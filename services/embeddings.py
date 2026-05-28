"""Text embeddings supporting multiple providers.

Configured via the EMBEDDINGS dict in Django settings (see config/settings.py).

Supported providers (set EMBEDDINGS_PROVIDER in .env):
- ollama   (local, uses OLLAMA_EMBED_MODEL)
- openai   (uses OPENAI_EMBED_MODEL, e.g. text-embedding-3-large)

The rest of the app (RAG, document upload, vectorstore) calls embed_text / embed_texts
without caring which backend is active.
"""

import logging
from typing import Iterable

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


class EmbeddingError(RuntimeError):
    pass


def _get_embeddings_cfg():
    """Return the effective embeddings configuration.

    Supports mixed providers:
    - EMBEDDINGS_PROVIDER=openai  → use OpenAI embedding model (e.g. text-embedding-3-large)
    - EMBEDDINGS_PROVIDER=ollama  → use Ollama embedding model (e.g. nomic-embed-text)

    When EMBEDDINGS_PROVIDER=ollama, this function merges the full OLLAMA settings
    (BASE_URL, EMBED_MODEL, TIMEOUT, etc.) so the legacy Ollama path works correctly.
    """
    emb = dict(getattr(settings, "EMBEDDINGS", {}) or {})
    provider = (emb.get("PROVIDER") or "ollama").lower()

    if provider == "openai":
        # For OpenAI we only need the keys that are already in EMBEDDINGS
        # (OPENAI_API_KEY and OPENAI_EMBED_MODEL). Fill sensible defaults.
        emb.setdefault("PROVIDER", "openai")
        emb.setdefault("OPENAI_EMBED_MODEL", "text-embedding-3-large")
        emb.setdefault("OPENAI_API_KEY", getattr(settings, "LLM", {}).get("OPENAI_API_KEY", ""))
        emb.setdefault("DIMENSION", 0)
        return emb

    # provider == "ollama" (or anything else → treat as ollama)
    ollama = dict(getattr(settings, "OLLAMA", {}) or {})
    # Start from OLLAMA block, then let explicit EMBEDDINGS keys override if present
    merged = {
        "PROVIDER": "ollama",
        **ollama,
        **emb,  # EMBEDDINGS_ keys can override OLLAMA_ keys if someone sets them
    }
    # Ensure we have a usable embed model name
    merged.setdefault("EMBED_MODEL", ollama.get("EMBED_MODEL") or "nomic-embed-text")
    merged.setdefault("BASE_URL", ollama.get("BASE_URL", "http://localhost:11434").rstrip("/"))
    merged.setdefault("TIMEOUT", ollama.get("TIMEOUT", 120))
    return merged


def _get_dimension_from_settings() -> int | None:
    """Return explicit dimension if set in EMBEDDINGS or PINECONE, else None."""
    emb = getattr(settings, "EMBEDDINGS", {}) or {}
    dim = emb.get("DIMENSION") or 0
    if dim:
        return int(dim)
    pin = getattr(settings, "PINECONE", {}) or {}
    dim = pin.get("DIMENSION") or 0
    if dim:
        return int(dim)
    return None


def _ollama_embed_texts(texts: Iterable[str], cfg: dict) -> list[list[float]]:
    """Embed using Ollama /api/embeddings."""
    base_url = cfg.get("BASE_URL", "http://localhost:11434").rstrip("/")
    # Support both EMBED_MODEL (from merged) and the original OLLAMA_EMBED_MODEL env var
    model = (
        cfg.get("EMBED_MODEL")
        or cfg.get("OLLAMA_EMBED_MODEL")
        or "nomic-embed-text"
    )
    timeout = int(cfg.get("TIMEOUT", 120))

    logger.info("Using Ollama embeddings: model=%s base_url=%s", model, base_url)

    vectors = []
    for text in texts:
        try:
            resp = requests.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Ollama embedding FAILED (model=%s): %s", model, exc)
            raise EmbeddingError(
                f"Ollama embedding request failed at {base_url} with model '{model}': {exc}. "
                "Is Ollama running and the model pulled?"
            ) from exc

        vector = resp.json().get("embedding")
        if not vector:
            raise EmbeddingError(f"Ollama returned empty embedding for model '{model}'.")
        vectors.append(vector)

    logger.debug("embedded %d text(s) via Ollama '%s' (dim=%d)", len(vectors), model, len(vectors[0]) if vectors else 0)
    return vectors


def _openai_embed_texts(texts: Iterable[str], cfg: dict) -> list[list[float]]:
    """Embed using OpenAI Embeddings API."""
    if OpenAI is None:
        raise EmbeddingError("openai package is not installed. Run: pip install openai")

    api_key = cfg.get("OPENAI_API_KEY") or getattr(settings, "LLM", {}).get("OPENAI_API_KEY", "")
    if not api_key:
        raise EmbeddingError("OPENAI_API_KEY is required for EMBEDDINGS_PROVIDER=openai")

    model = cfg.get("OPENAI_EMBED_MODEL") or "text-embedding-3-large"

    logger.info("Using OpenAI embeddings: model=%s", model)

    client = OpenAI(api_key=api_key)

    try:
        # OpenAI accepts a list of strings
        resp = client.embeddings.create(model=model, input=list(texts))
        vectors = [d.embedding for d in resp.data]
    except Exception as exc:  # noqa: BLE001
        logger.error("OpenAI embedding FAILED (model=%s): %s", model, exc)
        raise EmbeddingError(f"OpenAI embedding failed with model '{model}': {exc}") from exc

    logger.debug("embedded %d text(s) via OpenAI '%s' (dim=%d)", len(vectors), model, len(vectors[0]) if vectors else 0)
    return vectors


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed a list of strings using the configured provider (EMBEDDINGS_PROVIDER)."""
    cfg = _get_embeddings_cfg()
    provider = (cfg.get("PROVIDER") or "ollama").lower()

    if provider == "openai":
        return _openai_embed_texts(texts, cfg)
    elif provider == "ollama":
        return _ollama_embed_texts(texts, cfg)
    else:
        raise EmbeddingError(f"Unknown EMBEDDINGS_PROVIDER: {provider}")


def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns one float vector."""
    return embed_texts([text])[0]


def embedding_dimension() -> int:
    """Return the configured or probed embedding dimension.

    Priority:
    1. Explicit EMBEDDINGS_DIMENSION or PINECONE_DIMENSION in settings/.env
    2. Probe the model (one embedding call) for OpenAI or Ollama
    """
    explicit = _get_dimension_from_settings()
    if explicit:
        return explicit

    # Probe
    vec = embed_text("dimension probe")
    return len(vec)
