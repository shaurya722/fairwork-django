from django.conf import settings
from django.db.models import Count, Max, Subquery, OuterRef
from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from awards import ingest
from awards.models import AwardClause, NDISDocument
from services import llm as llm_service
from services import ndis_rag, rag, scraper, wages

from .models import ChatLog
from .serializers import (
    ChatLogSerializer,
    ChatRequestSerializer,
    NDISChatRequestSerializer,
    ScrapeRequestSerializer,
    SessionSummarySerializer,
    ShiftCalcRequestSerializer,
)

# Conversation memory tuning.
_HISTORY_TURNS = 10     # how many prior Q&A turns the chatbot remembers
_HISTORY_CHARS = 1500    # max characters kept from each remembered message


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
    """POST a question, get an intelligent answer from the unified chatbot.

    This endpoint handles EVERYTHING:
    - Fair Work award questions (with clause citations)
    - NDIS pricing questions (support categories, price limits)
    - SCHADS pay calculations (shifts, penalties, allowances)
    - Public holidays, overtime, casual loading, etc.

    The system automatically detects the question type and routes to:
    - services.rag (Fair Work + SCHADS calculations)
    - services.ndis_rag (NDIS pricing documents)

    Request:  {"message": "What are Sunday penalty rates?", "top_k": 5}
    Response: {"answer": "...", "sources": [...], "calculation": {...}, "meta": {...}}

    Every call is persisted to SQLite as a ChatLog row.
    """

    def post(self, request):
        request_data = ChatRequestSerializer(data=request.data)
        request_data.is_valid(raise_exception=True)
        data = request_data.validated_data
        session_id = data.get("session_id", "")
        question = data["message"]
        history = _recent_history(session_id)

        # Classify the question to route intelligently
        from services import llm as llm_service
        is_ndis = llm_service.classify_question(question)

        if is_ndis:
            # Route to NDIS RAG pipeline
            result = ndis_rag.answer_question(
                question=question,
                top_k=data.get("top_k"),
                session_id=session_id,
                history=history,
                year=None,  # use active document for latest year
            )
            # Prefix the stored question so we can identify NDIS conversations
            stored_question = f"[NDIS] {result['question']}"
        else:
            # Route to Fair Work award + SCHADS calculation pipeline
            result = rag.answer_question(
                question=question,
                top_k=data.get("top_k"),
                session_id=session_id,
                history=history,
            )
            stored_question = result["question"]

        # Persist the prompt request + response to SQLite.
        log = ChatLog.objects.create(
            question=stored_question,
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
                "ndis_document": result.get("ndis_document"),
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
                    "route": "ndis" if is_ndis else "award",
                },
            },
            status=200 if result["success"] else 502,
        )


class NDISChatAPIView(APIView):
    """POST a question, get an NDIS Pricing Arrangements answer.

    This endpoint is scoped to the NDIS pricing PDFs only — it never runs the
    SCHADS pay-calculation path. Retrieval targets the active document for the
    most recent year unless the request body includes ``"year"``.

    Request:  {"message": "What is the price limit for daily activities?",
               "session_id": "...", "top_k": 5, "year": "2024-25"}
    Response: {"answer": "...", "sources": [...], "ndis_document": {...}, "meta": {...}}

    Each call is persisted to ChatLog with a "[NDIS]" prefix on the question
    so the regular history view still works, but the two corpora can be
    separated when needed.
    """

    def post(self, request):
        request_data = NDISChatRequestSerializer(data=request.data)
        request_data.is_valid(raise_exception=True)
        data = request_data.validated_data
        session_id = data.get("session_id", "")
        year = (data.get("year") or "").strip() or None

        result = ndis_rag.answer_question(
            question=data["message"],
            top_k=data.get("top_k"),
            session_id=session_id,
            history=_recent_history(session_id),
            year=year,
        )

        # Persist the prompt request + response to SQLite. The "[NDIS]" prefix
        # on the stored question lets the existing history view filter / spot
        # NDIS conversations without a schema change.
        log = ChatLog.objects.create(
            question=f"[NDIS] {result['question']}",
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
                "ndis_document": result.get("ndis_document"),
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


class ShiftCalcAPIView(APIView):
    """POST a Shift Lifecycle Payload, get a step-by-step calc + Pydantic JSON.

    Runs the payload through the dedicated NDIS Backend Financial Reasoning
    prompt (services.llm.SHIFT_CALC_SYSTEM_PROMPT). The LLM emits a markdown
    reasoning block followed by a single JSON object matching the schema
    documented on the endpoint. The response separates the two so the client
    can render the reasoning AND consume the JSON without re-parsing.

    Request body:
        {
          "shift_id": "string (uuid)",                    # optional
          "employee_base_rate": 35.67,                     # optional, $/hr
          "session_id": "string",                          # optional
          "shift_lifecycle_payload": { ... full payload ... }
        }

    Response:
        {
          "shift_id": "...",
          "reasoning_markdown": "### Calculation Steps ...",
          "result": { ... Pydantic-shaped JSON ... },
          "meta": { "chat_model": "...", "llm_ms": 0 }
        }
    """

    def post(self, request):
        import time

        params = ShiftCalcRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        payload = data["shift_lifecycle_payload"]
        rate = data.get("employee_base_rate")
        shift_id = data.get("shift_id") or payload.get("shift_id") or ""
        session_id = data.get("session_id", "")

        started = time.perf_counter()
        try:
            result = llm_service.generate_shift_calculation(
                payload, employee_base_rate=rate
            )
        except llm_service.LLMError as exc:
            return Response(
                {"success": False, "error": str(exc)},
                status=502,
            )
        llm_ms = int((time.perf_counter() - started) * 1000)

        # Persist a compact ChatLog row so this call is auditable alongside
        # the rest of the chat traffic.
        parsed = result["result"]
        log = ChatLog.objects.create(
            question=f"[SHIFT_CALC] {shift_id or 'unnamed-shift'}",
            session_id=session_id,
            answer=result["raw"][:8000],
            sources=[],
            context_used="",
            chat_model=getattr(settings, "LLM", {}).get("PROVIDER", "ollama"),
            embed_model="",
            top_k=0,
            matches_found=0,
            retrieval_ms=0,
            llm_ms=llm_ms,
            total_ms=llm_ms,
            success=True,
            error="",
        )

        return Response(
            {
                "id": log.id,
                "shift_id": shift_id,
                "reasoning_markdown": result["reasoning"],
                "result": parsed,
                "success": True,
                "error": "",
                "meta": {
                    "chat_model": getattr(settings, "LLM", {}).get("PROVIDER", "ollama"),
                    "llm_ms": llm_ms,
                    "total_ms": llm_ms,
                },
            },
            status=200,
        )


class NDISDocumentsView(APIView):
    """GET the list of ingested NDIS pricing documents.

    Lets the frontend show which years are available and which one is active.
    """

    def get(self, request):
        docs = NDISDocument.objects.all().order_by("-year", "-version")
        return Response(
            {
                "results": [
                    {
                        "id": doc.id,
                        "year": doc.year,
                        "version": doc.version,
                        "title": doc.title,
                        "source_file": doc.source_file,
                        "is_active": doc.is_active,
                        "page_count": doc.page_count,
                        "chunk_count": doc.chunk_count,
                        "namespace": doc.pinecone_namespace,
                        "created_at": doc.created_at,
                    }
                    for doc in docs
                ]
            }
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


class ChatSessionsView(APIView):
    """GET a paginated list of chat sessions with summary metadata.

    Query params:
      ?page=1&limit=20
      ?search=some text     # filters sessions where the preview (first question) contains the text (case-insensitive)

    Response shape:
      {
        "results": [
          {
            "session_id": "...",
            "message_count": 12,
            "last_message_at": "2026-05-25T...",
            "preview": "What are Sunday penalty rates?"
          },
          ...
        ],
        "count": 42,
        "page": 1,
        "limit": 20,
        "total_pages": 3
      }

    Sorted by last activity descending (newest first).
    Used by the frontend to render a session sidebar / history list.
    """

    def get(self, request):
        # Pagination params
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            limit = max(1, int(request.query_params.get("limit", 20)))
        except (ValueError, TypeError):
            limit = 20
        limit = min(limit, 100)  # hard cap
        offset = (page - 1) * limit

        # Search param (filters on preview / first question)
        search = (request.query_params.get("search") or "").strip()

        # First question per session (chronological) → preview (scalar string or None)
        first_q_subq = (
            ChatLog.objects.filter(session_id=OuterRef("session_id"))
            .order_by("created_at")
            .values_list("question", flat=True)[:1]
        )

        qs = (
            ChatLog.objects.exclude(session_id="")
            .values("session_id")
            .annotate(
                message_count=Count("id"),
                last_message_at=Max("created_at"),
                preview=Subquery(first_q_subq),
            )
        )

        if search:
            qs = qs.filter(preview__icontains=search)

        qs = qs.order_by("-last_message_at")

        total = qs.count()
        paginated = qs[offset : offset + limit]
        data = SessionSummarySerializer(paginated, many=True).data

        return Response({
            "results": data,
            "count": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit else 0,
        })


class DeleteSessionView(APIView):
    """DELETE a chat session and all its logs.

    DELETE /api/chat/sessions/<session_id>/
    """

    def delete(self, request, session_id):
        if not session_id:
            return Response({"detail": "session_id required"}, status=400)
        deleted, _ = ChatLog.objects.filter(session_id=session_id).delete()
        return Response(status=204)


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
