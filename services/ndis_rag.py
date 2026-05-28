"""NDIS-only RAG pipeline.

Mirrors ``services.rag.answer_question`` but the retrieval is scoped to a
single :class:`awards.models.NDISDocument` — typically the active document for
the latest year. No SCHADS pay-calculation path is invoked here; this endpoint
exists so callers who only want NDIS pricing answers get a clean, predictable
response.
"""

from __future__ import annotations

import logging
import math
import time

from django.conf import settings

from awards.models import NDISDocument

from . import embeddings, llm, vectorstore

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(**kwargs):
        def decorator(fn):
            return fn
        return decorator


logger = logging.getLogger(__name__)


def _vector_summary(vector) -> str:
    if not vector:
        return "<empty vector>"
    norm = math.sqrt(sum(float(x) * float(x) for x in vector))
    preview = ", ".join(f"{float(x):.4f}" for x in vector[:8])
    return f"dim={len(vector)} norm={norm:.4f} head=[{preview}, ...]"


def pick_document(year: str | None = None) -> NDISDocument | None:
    """Return the NDIS document the query should search.

    Selection rules:
    1. If ``year`` is provided, return the active document for that year
       (falling back to any document for that year).
    2. Otherwise return the active document for the most recent year
       (falling back to the newest document overall).
    """
    if year:
        qs = NDISDocument.objects.filter(year=year)
        return qs.filter(is_active=True).order_by("-version", "-created_at").first() \
            or qs.order_by("-version", "-created_at").first()

    return (
        NDISDocument.objects.filter(is_active=True)
        .order_by("-year", "-version", "-created_at")
        .first()
        or NDISDocument.objects.order_by("-year", "-version", "-created_at").first()
    )


@traceable(run_type="chain", name="ndis-rag-pipeline")
def answer_question(question, top_k=None, session_id="", history=None, year=None):
    """Run the NDIS RAG pipeline for one question.

    ``year`` selects which yearly NDIS document to search (e.g. ``"2024-25"``);
    when omitted, the active document for the most recent year is used. The
    return shape matches ``services.rag.answer_question`` so the existing
    ChatLog table can persist the result without changes.
    """
    top_k = top_k or settings.RAG["TOP_K"]
    llm_cfg = getattr(settings, "LLM", {})
    ollama_cfg = getattr(settings, "OLLAMA", {})

    document = pick_document(year)

    result = {
        "question": question,
        "session_id": session_id,
        "answer": "",
        "sources": [],
        "context_used": "",
        "chat_model": llm_cfg.get("PROVIDER", "ollama"),
        "embed_model": ollama_cfg.get("EMBED_MODEL", "nomic-embed-text"),
        "top_k": top_k,
        "matches_found": 0,
        "retrieval_ms": 0,
        "llm_ms": 0,
        "total_ms": 0,
        "success": True,
        "error": "",
        "calculation": None,
        "ndis_document": None,
    }
    started = time.perf_counter()

    if document:
        result["ndis_document"] = {
            "id": document.id,
            "year": document.year,
            "version": document.version,
            "title": document.title,
            "is_active": document.is_active,
        }

    logger.info(
        "=== NDIS chat query | session=%r history_turns=%d year=%r doc=%s | %r",
        session_id, len(history or []), year,
        f"{document.year} {document.version}" if document else "<none>",
        question,
    )

    if not document:
        result["answer"] = (
            "No NDIS pricing document has been ingested yet. Ask an admin to "
            "run: python manage.py import_ndis_pdf <file.pdf> --year YYYY-YY "
            "--activate"
        )
        result["success"] = False
        result["error"] = "no_ndis_document"
        result["total_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    namespace = document.pinecone_namespace

    try:
        question_vector = embeddings.embed_text(question)
        logger.info("query embedding: %s", _vector_summary(question_vector))

        matches = vectorstore.query(question_vector, top_k, namespace=namespace)
        result["retrieval_ms"] = int((time.perf_counter() - started) * 1000)
        result["matches_found"] = len(matches)

        if matches:
            logger.info(
                "retrieved %d NDIS chunks from namespace %r:",
                len(matches), namespace,
            )
            for rank, match in enumerate(matches, 1):
                meta = match.get("metadata", {})
                logger.info(
                    "  #%d  score=%.4f  id=%s  section=%s  pages=%s-%s",
                    rank, match.get("score", 0.0), match.get("id", ""),
                    meta.get("section", ""),
                    meta.get("page_start", ""), meta.get("page_end", ""),
                )
        else:
            logger.warning(
                "no NDIS matches for namespace %r — index empty or no semantic match",
                namespace,
            )

        context_blocks = []
        for match in matches:
            meta = match["metadata"]
            text = meta.get("content", "")
            if text:
                context_blocks.append(text)
            result["sources"].append(
                {
                    "section": meta.get("section", ""),
                    "page_start": meta.get("page_start", ""),
                    "page_end": meta.get("page_end", ""),
                    "year": meta.get("year", document.year),
                    "version": meta.get("version", document.version),
                    "score": round(match["score"], 4),
                    "source_url": meta.get("source_url", ""),
                    "source_file": meta.get("source_file", ""),
                    "vector_id": match["id"],
                    "excerpt": text[:300],
                }
            )
        context = "\n\n---\n\n".join(context_blocks)
        result["context_used"] = context

        document_label = f"NDIS Pricing Arrangements {document.year}"
        if document.version:
            document_label += f" {document.version}"

        llm_started = time.perf_counter()
        if not context:
            result["answer"] = (
                f"I could not find anything matching that in the {document_label}. "
                "Try rephrasing or include the support category, item number, "
                "or section name you have in mind."
            )
        else:
            answer = llm.generate_ndis_answer(
                question, context, history=history, document_label=document_label
            )
            result["answer"] = answer
        result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)

        logger.info(
            "NDIS RAG answer in %dms (%d matches) | %r",
            result["llm_ms"], result["matches_found"], result["answer"][:200],
        )

    except Exception as exc:  # noqa: BLE001 - surfaced to the caller via result
        logger.error("NDIS RAG pipeline error: %s: %s", type(exc).__name__, exc)
        result["success"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        if not result["answer"]:
            result["answer"] = (
                "Sorry, I could not process your NDIS pricing question right now."
            )

    result["total_ms"] = int((time.perf_counter() - started) * 1000)
    return result
