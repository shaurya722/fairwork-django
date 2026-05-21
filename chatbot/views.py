from django.conf import settings
from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from awards import ingest
from awards.models import AwardClause
from services import rag, scraper, wages

from .models import ChatLog
from .serializers import (
    ChatLogSerializer,
    ChatRequestSerializer,
    ScrapeRequestSerializer,
)

# Conversation memory tuning.
_HISTORY_TURNS = 6      # how many prior Q&A turns the chatbot remembers
_HISTORY_CHARS = 700    # max characters kept from each remembered message


def _recent_history(session_id):
    """Recent turns for a session as chat messages — the chatbot's memory.

    Prior questions and answers are replayed to the LLM so the user does not
    need to repeat earlier context (their hourly rate, employment type, etc.).
    Returns an oldest-first list of ``{"role", "content"}`` dicts.
    """
    if not session_id:
        return []
    rows = list(
        ChatLog.objects.filter(session_id=session_id, success=True)
        .order_by("-id")[:_HISTORY_TURNS]
    )
    messages = []
    for row in reversed(rows):
        messages.append({"role": "user", "content": row.question[:_HISTORY_CHARS]})
        messages.append({"role": "assistant", "content": row.answer[:_HISTORY_CHARS]})
    return messages


class ChatAPIView(APIView):
    """POST a question, get a Fair Work award answer with clause citations.

    Request:  {"message": "What are Sunday penalty rates?", "top_k": 5}
    Response: {"answer": "...", "sources": [...], "meta": {...}}

    Every call is persisted to SQLite as a ChatLog row.
    """

    def post(self, request):
        request_data = ChatRequestSerializer(data=request.data)
        request_data.is_valid(raise_exception=True)
        data = request_data.validated_data
        session_id = data.get("session_id", "")

        result = rag.answer_question(
            question=data["message"],
            top_k=data.get("top_k"),
            session_id=session_id,
            history=_recent_history(session_id),
        )

        # Persist the prompt request + response to SQLite.
        log = ChatLog.objects.create(
            question=result["question"],
            session_id=result["session_id"],
            answer=result["answer"],
            sources=result["sources"],
            context_used=result["context_used"],
            chat_model=result["chat_model"],
            embed_model=result["embed_model"],
            top_k=result["top_k"],
            matches_found=result["matches_found"],
            retrieval_ms=result["retrieval_ms"],
            llm_ms=result["llm_ms"],
            total_ms=result["total_ms"],
            success=result["success"],
            error=result["error"],
        )

        return Response(
            {
                "id": log.id,
                "question": result["question"],
                "answer": result["answer"],
                "sources": result["sources"],
                "calculation": result.get("calculation"),
                "success": result["success"],
                "error": result["error"],
                "meta": {
                    "chat_model": result["chat_model"],
                    "embed_model": result["embed_model"],
                    "top_k": result["top_k"],
                    "matches_found": result["matches_found"],
                    "retrieval_ms": result["retrieval_ms"],
                    "llm_ms": result["llm_ms"],
                    "total_ms": result["total_ms"],
                },
            },
            status=200 if result["success"] else 502,
        )


class ChatHistoryView(generics.ListAPIView):
    """GET the most recent chat logs. Filter with ?session_id=..."""

    serializer_class = ChatLogSerializer

    def get_queryset(self):
        queryset = ChatLog.objects.all()
        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        return queryset[:100]


class ScrapeAwardView(APIView):
    """POST: re-scrape the Fair Work award and refresh the stored clauses.

    Fetches the award page with BeautifulSoup (``services.scraper``), re-chunks
    it into SQLite, then augments the minimum weekly-wage clauses (15, 16, 17)
    with an hourly-rate column — the weekly wage divided by the 38-hour week.

    Request body (every field optional):
        {"url": "https://awards.fairwork.gov.au/MA000100.html",
         "code": "MA000100", "fresh": false}

    Response: a scrape summary plus the structured wage rates (classification,
    weekly rate and hourly rate) for clauses 15-17.
    """

    def post(self, request):
        params = ScrapeRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        url = data.get("url") or settings.AWARD["URL"]
        code = data.get("code") or settings.AWARD["CODE"]
        fresh = data.get("fresh", False)

        # 1. Scrape + chunk the award page with BeautifulSoup.
        try:
            chunks = scraper.scrape_award(url, code, settings.AWARD["CHUNK_CHARS"])
        except scraper.ScrapeError as exc:
            return Response({"success": False, "error": str(exc)}, status=502)

        # 2. Store the chunks, then add hourly rates to the wage clauses.
        created, updated, removed = ingest.store_clauses(chunks, code, fresh=fresh)
        wage_clauses_updated = wages.apply_hourly_rates(award_code=code)

        # 3. Return the structured wage rates so the caller sees the result.
        wage_rates = []
        for clause in AwardClause.objects.filter(
            award_code=code, clause_no__in=list(wages.WAGE_CLAUSE_NUMBERS)
        ).order_by("clause_no", "chunk_index"):
            wage_rates.extend(
                wages.extract_wage_rates(clause.content, clause.clause_no)
            )

        return Response(
            {
                "success": True,
                "award_code": code,
                "source_url": url,
                "weekly_hours": float(wages.WEEKLY_HOURS),
                "scraped_chunks": len(chunks),
                "created": created,
                "updated": updated,
                "removed": removed,
                "wage_clauses_updated": wage_clauses_updated,
                "wage_rates": wage_rates,
                "next": "python manage.py index_award  # re-embed updated clauses",
            },
            status=200,
        )


class HealthView(APIView):
    """GET a quick status snapshot of the chatbot's data and config."""

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "award": settings.AWARD["CODE"],
                "clauses_in_sqlite": AwardClause.objects.count(),
                "clauses_indexed": AwardClause.objects.filter(is_indexed=True).count(),
                "chat_logs": ChatLog.objects.count(),
                "llm": {
                    "provider": getattr(settings, "LLM", {}).get("PROVIDER", "ollama"),
                },
                "ollama": {
                    "base_url": settings.OLLAMA.get("BASE_URL", ""),
                    "chat_model": settings.OLLAMA.get("CHAT_MODEL", ""),
                    "embed_model": settings.OLLAMA.get("EMBED_MODEL", ""),
                },
                "pinecone": {
                    "index": settings.PINECONE["INDEX_NAME"],
                    "namespace": settings.PINECONE["NAMESPACE"],
                    "api_key_set": bool(settings.PINECONE["API_KEY"]),
                },
            }
        )
