"""Text embeddings via a local Ollama model.

Uses the Ollama HTTP API (`/api/embeddings`). The default model is
``nomic-embed-text``; override with the OLLAMA_EMBED_MODEL env var.
"""

import requests
from django.conf import settings


class EmbeddingError(RuntimeError):
    pass


def _cfg():
    return settings.OLLAMA


def embed_texts(texts):
    """Embed a list of strings. Returns a list of float vectors."""
    cfg = _cfg()
    vectors = []
    for text in texts:
        try:
            resp = requests.post(
                f"{cfg['BASE_URL']}/api/embeddings",
                json={"model": cfg["EMBED_MODEL"], "prompt": text},
                timeout=cfg["TIMEOUT"],
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EmbeddingError(
                f"Ollama embedding request failed ({cfg['BASE_URL']}): {exc}. "
                f"Is Ollama running and is '{cfg['EMBED_MODEL']}' pulled?"
            ) from exc
        vector = resp.json().get("embedding")
        if not vector:
            raise EmbeddingError(
                f"Ollama returned an empty embedding for model '{cfg['EMBED_MODEL']}'. "
                f"Pull it with: ollama pull {cfg['EMBED_MODEL']}"
            )
        vectors.append(vector)
    return vectors


def embed_text(text):
    """Embed a single string. Returns one float vector."""
    return embed_texts([text])[0]


def embedding_dimension():
    """Return the embedding model's vector dimension (one probe call)."""
    return len(embed_text("dimension probe"))
