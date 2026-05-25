"""RAG orchestration: question -> embed -> retrieve -> ground -> answer.

No background workers are involved - the whole pipeline runs synchronously
inside the request, exactly as the chat API needs it.
"""

import json
import logging
import math
import re
import time
from datetime import date, datetime

from django.conf import settings

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(**kwargs):
        def decorator(fn):
            return fn
        return decorator

from . import embeddings, holidays, llm, schads, vectorstore, wages

# Pipeline tracer — every chat query is logged here: the query text, its
# embedding vector summary, the similar vectors retrieved with their scores,
# the path taken (calculation vs RAG) and the answer. See logs/chatbot.log.
logger = logging.getLogger(__name__)


def _vector_summary(vector) -> str:
    """One-line summary of an embedding vector for the logs.

    Reports the dimension, L2 norm and the first few components so a query's
    vector can be eyeballed without dumping hundreds of floats.
    """
    if not vector:
        return "<empty vector>"
    norm = math.sqrt(sum(float(x) * float(x) for x in vector))
    preview = ", ".join(f"{float(x):.4f}" for x in vector[:8])
    return f"dim={len(vector)} norm={norm:.4f} head=[{preview}, ...]"


@traceable(run_type="chain", name="rag-pipeline")
def answer_question(question, top_k=None, session_id="", history=None):
    """Run the full retrieval-augmented pipeline for one question.

    ``history`` is the conversation memory: a list of prior
    ``{"role", "content"}`` turns replayed to the LLM so the user does not
    have to repeat earlier context.

    Returns a dict ready to be saved to ``chatbot.ChatLog`` and serialised
    in the API response. Never raises - failures are captured in the result.
    """
    top_k = top_k or settings.RAG["TOP_K"]
    llm_cfg = getattr(settings, "LLM", {})
    ollama_cfg = getattr(settings, "OLLAMA", {})
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
    }
    started = time.perf_counter()

    logger.info(
        "=== chat query | session=%r history_turns=%d | %r",
        session_id, len(history or []), question,
    )

    # 0. Pay-calculation intent — run the SCHADS engine instead of RAG.
    if _looks_like_calculation(question):
        logger.info("path=CALCULATION (matched a pay-calculation hint)")
        try:
            if _try_calculation(question, result, started, history):
                result["total_ms"] = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "calculation done in %dms | answer=%r",
                    result["total_ms"], result["answer"][:200],
                )
                return result
            logger.info("not a calculation after extraction — falling back to RAG")
        except Exception as exc:  # noqa: BLE001 - silently fall back to RAG on failure
            logger.warning("calculation path failed (%s) — falling back to RAG", exc)
    else:
        logger.info("path=RAG (no pay-calculation hint matched)")

    try:
        # 1. Embed the question into a query vector.
        question_vector = embeddings.embed_text(question)
        logger.info("query embedding: %s", _vector_summary(question_vector))

        # 2. Retrieve the most similar award vectors from the vector store.
        matches = vectorstore.query(question_vector, top_k)
        result["retrieval_ms"] = int((time.perf_counter() - started) * 1000)
        result["matches_found"] = len(matches)
        if matches:
            logger.info(
                "retrieved %d similar vectors (top_k=%d), by similarity score:",
                len(matches), top_k,
            )
            for rank, match in enumerate(matches, 1):
                meta = match.get("metadata", {})
                logger.info(
                    "  #%d  score=%.4f  id=%s  clause=%s  title=%r",
                    rank, match.get("score", 0.0), match.get("id", ""),
                    meta.get("clause_no", ""), meta.get("title", ""),
                )
        else:
            logger.warning(
                "no similar vectors returned — index empty, or the embedding "
                "did not match anything. Answering conversationally instead."
            )

        # 3. Build the grounding context and source citations.
        context_blocks = []
        for match in matches:
            meta = match["metadata"]
            text = meta.get("content", "")
            if text:
                context_blocks.append(text)
            result["sources"].append(
                {
                    "clause_no": meta.get("clause_no", ""),
                    "title": meta.get("title", ""),
                    "part": meta.get("part", ""),
                    "score": round(match["score"], 4),
                    "source_url": meta.get("source_url", ""),
                    "vector_id": match["id"],
                    "excerpt": text[:300],
                }
            )
        context = "\n\n---\n\n".join(context_blocks)
        result["context_used"] = context

        # 4. Generate the answer.
        llm_started = time.perf_counter()
        if not context:
            # Nothing retrieved — stay supportive instead of dead-ending on a
            # canned refusal. Use the conversation memory + SCHADS knowledge.
            logger.info("no grounding context — using supportive conversational path")
            result["answer"] = llm.generate_followup_answer(question, "", history)
        else:
            answer = llm.generate_answer(question, context, history=history)
            if _is_refusal(answer):
                # The retrieved clauses did not contain the answer — most
                # often a follow-up about an earlier turn ("explain that").
                # Retry conversationally so the bot stays helpful.
                logger.info(
                    "grounded answer was a refusal — retrying via supportive path"
                )
                answer = llm.generate_followup_answer(question, context, history)
            result["answer"] = answer
        result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
        logger.info(
            "RAG answer in %dms (%d matches) | %r",
            result["llm_ms"], result["matches_found"], result["answer"][:200],
        )

    except Exception as exc:  # noqa: BLE001 - surfaced to the caller via result
        logger.error("RAG pipeline error: %s: %s", type(exc).__name__, exc)
        # Last resort — the vector store / embedder may be down. Still try to
        # answer from conversation memory before giving up.
        try:
            result["answer"] = llm.generate_followup_answer(question, "", history)
            logger.info("recovered with supportive conversational answer")
        except Exception:  # noqa: BLE001
            result["success"] = False
            result["error"] = f"{type(exc).__name__}: {exc}"
            if not result["answer"]:
                result["answer"] = "Sorry, I could not process your question right now."

    result["total_ms"] = int((time.perf_counter() - started) * 1000)
    return result


# The exact string the strict grounded prompt emits when the retrieved clauses
# do not contain the answer. Detected so the bot can retry conversationally.
_NO_ANSWER = "I could not find this in the award."


def _is_refusal(answer: str) -> bool:
    """True if the grounded LLM answer is the canned "not in the award" reply."""
    return (answer or "").strip().lower().startswith(_NO_ANSWER.lower().rstrip("."))


# ---------------------------------------------------------------------------
# SCHADS pay-calculation path
# ---------------------------------------------------------------------------

# A question only goes down the calculation path if it contains a number AND
# one of these hints. Anything else stays on the plain RAG path, so ordinary
# clause lookups never pay for the extra extraction call.
_CALC_HINTS = (
    "calculat", "how much", "earn", "pay for", "paid for", "owe", "payslip",
    "gross", "wage", "salary", "worked", "work ", "shift", "overtime",
    "sleepover", "roster", "hours", "hrs", "/hr", "per hour", "penalty",
    "total pay", "take home",
)


def _looks_like_calculation(question: str) -> bool:
    """Cheap heuristic gate before spending an LLM call on extraction."""
    q = (question or "").lower()
    has_number = any(ch.isdigit() for ch in q)
    return has_number and any(hint in q for hint in _CALC_HINTS)


# Words / patterns that mean the user actually named a date. When none appear,
# the shift date is an assumption and the answer says so — the day of the week
# changes the weekend / public-holiday penalty rate.
_DATE_WORDS = {
    "today", "tonight", "tomorrow", "yesterday",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec",
}
_DATE_NUM_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}|\b\d{1,2}(st|nd|rd|th)\b")


def _question_mentions_date(question: str) -> bool:
    """True if the question names a date / weekday / month, false otherwise."""
    q = (question or "").lower()
    if _DATE_NUM_RE.search(q):
        return True
    return bool(set(re.findall(r"[a-z]+", q)) & _DATE_WORDS)


def _assumed_date_note(payload: dict) -> str:
    """A note stating which shift date the engine used.

    Appended only when the user gave no date, so the assumption is visible —
    a Wednesday and a Saturday produce very different pay.
    """
    try:
        first = payload["shifts"][0]["segments"][0]["start"]
        moment = datetime.fromisoformat(str(first))
    except Exception:  # noqa: BLE001 - never break the answer over a note
        return ""
    return (
        f"\n\n📅 Note: no date was given, so this uses "
        f"{moment:%A, %d %b %Y}. Saturday, Sunday and public-holiday rates "
        f"differ from weekdays — tell me the actual shift date if it differs."
    )


def _try_calculation(question, result, started, history=None) -> bool:
    """Run the SCHADS engine for a pay question.

    ``history`` (conversation memory) is passed to extraction so a follow-up
    like "what about a 10-hour shift?" inherits the rate and employment type
    the user already gave.

    Returns True if the question was a calculation (handled, ``result``
    populated), or False if it was not — in which case the caller falls back
    to the normal RAG pipeline.
    """
    llm_started = time.perf_counter()

    extraction = llm.extract_calculation(
        question, date.today().isoformat(), history=history
    )
    if not extraction or not extraction.get("is_calculation"):
        return False  # not a calculation — let RAG handle it.

    payload = extraction.get("payload") or {}

    # Defensive: if the LLM incorrectly listed "base_hourly_rate" as missing
    # but the user *did* provide the three identifiers, clear it from the
    # missing list. The lookup below will populate the rate.
    emp = payload.get("employee") or {}
    has_identifiers = bool(
        emp.get("stream")
        and emp.get("classification_level") is not None
        and emp.get("pay_point") is not None
    )
    if has_identifiers and extraction.get("missing"):
        extraction["missing"] = [
            m for m in extraction["missing"]
            if m not in ("base_hourly_rate", "hourly rate", "hourly_rate")
        ]

    # Inject sensible defaults for optional fields so the LLM does not
    # have to guess them.  Only truly required fields are:
    #   - employment_type, base_hourly_rate, shifts[].segments[].start/end
    _inject_calc_defaults(payload, question)

    # If the user gave a stream + level + pay_point but no rate, look it up
    # from the scraped wage clauses before falling back to asking.
    emp = payload.get("employee") or {}
    if not emp.get("base_hourly_rate"):
        stream = emp.get("stream")
        level = emp.get("classification_level")
        pay_point = emp.get("pay_point")
        if stream and level is not None and pay_point is not None:
            looked_up = wages.lookup_hourly_rate(stream, level, pay_point)
            logger.info(
                "wage lookup for stream=%s level=%s pay_point=%s → %s",
                stream, level, pay_point, looked_up,
            )
            if looked_up:
                emp["base_hourly_rate"] = looked_up
            else:
                logger.warning(
                    "Wage lookup FAILED for %s L%s PP%s. "
                    "The award wage tables may not be scraped/augmented. "
                    "Run: python manage.py scrape_award --fresh && python manage.py index_award",
                    stream, level, pay_point,
                )

    # Apply the stored public holidays so a shift worked on one gets the
    # right penalty loading without the user having to list the dates.
    _inject_public_holidays(payload)

    logger.info(
        "extracted payload: employee=%s shifts=%s holidays=%d",
        emp,
        [
            [seg.get("start"), seg.get("end")]
            for sh in payload.get("shifts") or []
            for seg in (sh.get("segments") or [])
        ],
        len(payload.get("public_holidays") or []),
    )

    # Validate required fields manually so we can give a clear message.
    missing = _find_missing_required(payload)

    if missing:
        logger.info("calculation blocked — missing required fields: %s", missing)

        # Special case: the user gave stream + level + pay_point.
        # If after lookup we still have no rate, the award simply does not
        # define that exact combination (e.g. Home Care Level 2 only has
        # pay points 1 and 2). We already attempted a graceful fallback inside
        # lookup_hourly_rate. If we reach here with no rate, surface a clear
        # diagnostic instead of the generic "still need hourly rate" prompt.
        emp = payload.get("employee") or {}
        has_identifiers = bool(
            emp.get("stream")
            and emp.get("classification_level") is not None
            and emp.get("pay_point") is not None
        )
        if has_identifiers and not emp.get("base_hourly_rate"):
            result["answer"] = (
                "I understood the classification: "
                f"{emp.get('stream')} Level {emp.get('classification_level')} "
                f"Pay point {emp.get('pay_point')} ({emp.get('employment_type', '').lower() or 'casual'}).\n\n"
                "The SCHADS award (MA000100) does not define that exact pay point for this level "
                "in the published wage tables (clause 15/16/17).\n\n"
                "The system attempted to fall back to the highest rate defined for the same level.\n\n"
                "Please either:\n"
                "• Provide your actual hourly rate explicitly (recommended — your organisation may pay above the award minimum), or\n"
                "• Confirm the correct pay point that exists in the award for this stream/level."
            )
            result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
            return True

        # Generic case (user did not give classification details).
        result["answer"] = (
            "To calculate your SCHADS pay I still need: "
            + "; ".join(str(m) for m in missing)
            + ".\n\nPlease include your hourly rate, employment type "
            "(casual or permanent), and each shift's start and end date-time."
        )
        result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
        return True

    # Run the verified calculation engine.
    try:
        calc = schads.calculate_pay(payload)
    except schads.CalculationError as exc:
        result["answer"] = (
            f"I couldn't calculate that: {exc}\n\n"
            "Please rephrase with the hourly rate, employment type, and the "
            "exact shift start and end times."
        )
        result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
        return True

    result["calculation"] = calc
    result["context_used"] = json.dumps(calc)

    totals = calc.get("totals", {})
    logger.info(
        "SCHADS engine: gross=$%s (work $%s + allowances $%s), %d line items",
        totals.get("gross"), totals.get("work"), totals.get("allowances"),
        len(calc.get("line_items", [])),
    )
    for item in calc.get("line_items", []):
        logger.info(
            "  line: %s | %sh x%s = $%s | rule=%s",
            item.get("description"), item.get("hours", "-"),
            item.get("multiplier", "-"), item.get("amount"), item.get("rule"),
        )

    # Explain the result in plain English (deterministic fallback if the LLM
    # explanation fails — the figures are already computed and verified).
    try:
        result["answer"] = llm.explain_calculation(question, calc)
    except Exception:  # noqa: BLE001
        result["answer"] = _format_calculation(calc)

    # If the user gave no date, the shift date is an assumption — show it, so
    # an ambiguous "8pm to 6am" can never silently land on a different day.
    if not _question_mentions_date(question):
        note = _assumed_date_note(payload)
        if note:
            result["answer"] += note
            logger.info("no date in question — appended assumed-date note")

    result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
    return True


def _inject_calc_defaults(payload: dict, question: str = ""):
    """Fill in sensible defaults for optional SCHADS fields."""
    emp = payload.setdefault("employee", {})
    if not isinstance(emp, dict):
        payload["employee"] = emp = {}

    # Normalise stream names so the lookup still works when the LLM returns
    # a lowercase or colloquial variant (e.g. "homecare" instead of "HOME_CARE").
    _STREAM_ALIASES = {
        "homecare": "HOME_CARE",
        "home care": "HOME_CARE",
        "aged care": "HOME_CARE",
        "in-home": "HOME_CARE",
        "social and community services": "SOCIAL_COMMUNITY_SERVICES",
        "scs": "SOCIAL_COMMUNITY_SERVICES",
        "disability support": "SOCIAL_COMMUNITY_SERVICES",
        "disability services": "SOCIAL_COMMUNITY_SERVICES",
        "community services": "SOCIAL_COMMUNITY_SERVICES",
        "crisis accommodation": "CRISIS_ACCOMMODATION",
        "crisis": "CRISIS_ACCOMMODATION",
        "family day care": "FAMILY_DAY_CARE",
        "fdc": "FAMILY_DAY_CARE",
    }
    raw_stream = (emp.get("stream") or "").strip().lower()
    if raw_stream:
        emp["stream"] = _STREAM_ALIASES.get(raw_stream, emp["stream"])

    emp.setdefault("stream", None)
    emp.setdefault("classification_level", None)
    emp.setdefault("pay_point", None)
    emp.setdefault("disability_services_work", False)

    tenant = payload.setdefault("tenant_config", {})
    if not isinstance(tenant, dict):
        payload["tenant_config"] = tenant = {}
    tenant.setdefault("meal_allowance", False)
    tenant.setdefault("uniform_allowance", False)
    tenant.setdefault("laundry_allowance", False)
    tenant.setdefault("weekly_overtime", False)
    tenant.setdefault("overtime_period", "WEEK")

    # Detect sleepover intent from the user message when the LLM missed it.
    q_lower = question.lower()
    has_sleepover_keyword = any(
        kw in q_lower for kw in ("sleepover", "sleep over", "slept over")
    )

    for shift in payload.get("shifts") or []:
        if isinstance(shift, dict):
            # If the user mentioned sleepover but the LLM left it false, flip it.
            if has_sleepover_keyword and not shift.get("is_sleepover"):
                shift["is_sleepover"] = True
            shift.setdefault("is_sleepover", False)
            shift.setdefault("km", 0)
            shift.setdefault("had_break", True)


def _inject_public_holidays(payload: dict):
    """Merge the stored public-holiday dates into the calculation payload.

    The SCHADS engine treats ``public_holidays`` as a set of dates, so any
    the user already supplied are kept and the DB dates are added. A failed
    lookup never blocks the calculation.
    """
    try:
        stored = holidays.holiday_dates()
    except Exception:  # noqa: BLE001 - never block a calc on holiday lookup
        return
    existing = payload.get("public_holidays") or []
    payload["public_holidays"] = sorted(
        {str(d)[:10] for d in existing} | set(stored)
    )


def _find_missing_required(payload: dict) -> list[str]:
    """Return a list of human-readable missing *required* fields."""
    missing: list[str] = []
    emp = payload.get("employee") or {}
    if not emp.get("employment_type"):
        missing.append("employment type (casual or permanent)")
    if not emp.get("base_hourly_rate"):
        missing.append("hourly rate")

    shifts = payload.get("shifts") or []
    if not shifts:
        missing.append("at least one shift with start and end times")
    else:
        has_valid_segment = False
        for shift in shifts:
            if not isinstance(shift, dict):
                continue
            for seg in shift.get("segments") or []:
                if isinstance(seg, dict) and seg.get("start") and seg.get("end"):
                    has_valid_segment = True
                    break
            if has_valid_segment:
                break
        if not has_valid_segment:
            missing.append("at least one shift with start and end times")
    return missing


def _format_calculation(calc: dict) -> str:
    """Plain-text rendering of an engine result — used if the LLM is down."""
    lines = ["Here is your SCHADS pay calculation:", ""]
    for item in calc.get("line_items", []):
        if item.get("multiplier") is not None:
            lines.append(
                f"• {item['description']}: {item.get('hours', '?')}h "
                f"× {item['multiplier']} = ${item['amount']} ({item['rule']})"
            )
        else:
            lines.append(f"• {item['description']}: ${item['amount']} ({item['rule']})")
    totals = calc.get("totals", {})
    lines.append("")
    lines.append(
        f"Work ${totals.get('work', 0)} + allowances "
        f"${totals.get('allowances', 0)} = gross ${totals.get('gross', 0)}."
    )
    for warning in calc.get("warnings", []):
        lines.append(f"Note: {warning}")
    return "\n".join(lines)
