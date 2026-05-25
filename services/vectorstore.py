"""Pinecone vector store wrapper.

Stores one vector per award chunk, with the chunk text and clause metadata
in the vector payload so retrieval returns everything the LLM needs.
"""

import logging
import time

from django.conf import settings

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:  # pragma: no cover
    Pinecone = None
    ServerlessSpec = None

logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    pass


_client = None


def _cfg():
    return settings.PINECONE


def _attr(obj, key, default=None):
    """Read ``key`` from a dict or an SDK model object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    try:
        return obj[key]
    except (KeyError, TypeError, IndexError):
        return default


def get_client():
    global _client
    if Pinecone is None:
        raise VectorStoreError("The 'pinecone' package is not installed. Run: pip install pinecone")
    cfg = _cfg()
    if not cfg["API_KEY"]:
        raise VectorStoreError(
            "PINECONE_API_KEY is not set. Add it to your .env file "
            "(get a key at https://app.pinecone.io)."
        )
    if _client is None:
        _client = Pinecone(api_key=cfg["API_KEY"])
    return _client


def ensure_index(dimension=None):
    """Create the serverless index if it does not exist; return the handle.

    ``dimension`` defaults to ``PINECONE["DIMENSION"]`` so the index
    always matches the configured embedding model. Passing an explicit
    value validates that it matches the config (warns but does not block).
    """
    cfg = _cfg()
    configured_dim = cfg["DIMENSION"]
    target_dim = dimension if dimension is not None else configured_dim

    if dimension is not None and dimension != configured_dim:
        logger.warning(
            "ensure_index called with dimension=%d but PINECONE_DIMENSION=%d. "
            "Consider updating the PINECONE_DIMENSION env var or recreating the index.",
            dimension, configured_dim,
        )

    pc = get_client()
    if not pc.has_index(cfg["INDEX_NAME"]):
        pc.create_index(
            name=cfg["INDEX_NAME"],
            dimension=target_dim,
            metric=cfg["METRIC"],
            spec=ServerlessSpec(cloud=cfg["CLOUD"], region=cfg["REGION"]),
        )
        for _ in range(60):
            status = pc.describe_index(cfg["INDEX_NAME"]).status
            if _attr(status, "ready", False):
                break
            time.sleep(1)
    return pc.Index(cfg["INDEX_NAME"])


def get_index():
    cfg = _cfg()
    pc = get_client()
    if not pc.has_index(cfg["INDEX_NAME"]):
        raise VectorStoreError(
            f"Pinecone index '{cfg['INDEX_NAME']}' does not exist. "
            f"Run: python manage.py index_award"
        )
    return pc.Index(cfg["INDEX_NAME"])


def upsert(vectors, batch_size=50):
    """Upsert vectors: list of {id, values, metadata}. Returns the count."""
    cfg = _cfg()
    if vectors:
        vec_dim = len(vectors[0]["values"])
        configured_dim = cfg["DIMENSION"]
        if vec_dim != configured_dim:
            raise VectorStoreError(
                f"Vector dimension {vec_dim} does not match PINECONE_DIMENSION={configured_dim}. "
                f"Set PINECONE_DIMENSION={vec_dim} in your environment and recreate the index."
            )
        index = ensure_index(vec_dim)
    else:
        index = get_index()
    for start in range(0, len(vectors), batch_size):
        index.upsert(vectors=vectors[start:start + batch_size], namespace=cfg["NAMESPACE"])
    return len(vectors)


def query(vector, top_k):
    """Search the index. Returns a list of {id, score, metadata} dicts."""
    cfg = _cfg()
    configured_dim = cfg["DIMENSION"]
    vec_dim = len(vector)
    if vec_dim != configured_dim:
        raise VectorStoreError(
            f"Query vector dimension {vec_dim} does not match PINECONE_DIMENSION={configured_dim}. "
            f"Set PINECONE_DIMENSION={vec_dim} in your environment and recreate the index."
        )
    try:
        index = get_index()
        response = index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            namespace=cfg["NAMESPACE"],
        )
    except Exception as exc:  # noqa: BLE001 - logged then re-raised for the pipeline
        logger.error(
            "vector store query FAILED (index=%s namespace=%s): %s",
            cfg["INDEX_NAME"], cfg["NAMESPACE"], exc,
        )
        raise
    matches = _attr(response, "matches", []) or []
    results = []
    for match in matches:
        metadata = _attr(match, "metadata", {}) or {}
        results.append(
            {
                "id": _attr(match, "id", ""),
                "score": float(_attr(match, "score", 0.0) or 0.0),
                "metadata": dict(metadata),
            }
        )
    return results


def delete_all():
    """Remove every vector in the configured namespace."""
    cfg = _cfg()
    index = get_index()
    try:
        index.delete(delete_all=True, namespace=cfg["NAMESPACE"])
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "namespace" in msg or "not found" in msg:
            logger.info("Namespace '%s' already empty or missing; nothing to delete.", cfg["NAMESPACE"])
            return
        raise


def stats():
    """Return index statistics (vector counts, dimension)."""
    index = get_index()
    return index.describe_index_stats()
