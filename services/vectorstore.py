"""Pinecone vector store wrapper.

Stores one vector per award chunk, with the chunk text and clause metadata
in the vector payload so retrieval returns everything the LLM needs.
"""

import time

from django.conf import settings

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:  # pragma: no cover
    Pinecone = None
    ServerlessSpec = None


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


def ensure_index(dimension):
    """Create the serverless index if it does not exist; return the handle."""
    cfg = _cfg()
    pc = get_client()
    if not pc.has_index(cfg["INDEX_NAME"]):
        pc.create_index(
            name=cfg["INDEX_NAME"],
            dimension=dimension,
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
    index = ensure_index(len(vectors[0]["values"])) if vectors else get_index()
    for start in range(0, len(vectors), batch_size):
        index.upsert(vectors=vectors[start:start + batch_size], namespace=cfg["NAMESPACE"])
    return len(vectors)


def query(vector, top_k):
    """Search the index. Returns a list of {id, score, metadata} dicts."""
    cfg = _cfg()
    index = get_index()
    response = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        namespace=cfg["NAMESPACE"],
    )
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
    index.delete(delete_all=True, namespace=cfg["NAMESPACE"])


def stats():
    """Return index statistics (vector counts, dimension)."""
    index = get_index()
    return index.describe_index_stats()
