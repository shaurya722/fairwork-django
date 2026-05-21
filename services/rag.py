"""RAG orchestration: question -> embed -> retrieve -> ground -> answer.

No background workers are involved - the whole pipeline runs synchronously
inside the request, exactly as the chat API needs it.
"""

import json
import time
from datetime import date

from django.conf import settings

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(**kwargs):
        def decorator(fn):
            return fn
        return decorator

from . import embeddings, holidays, llm, schads, vectorstore, wages


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

    # 0. Pay-calculation intent — run the SCHADS engine instead of RAG.
    if _looks_like_calculation(question):
        try:
            if _try_calculation(question, result, started, history):
                result["total_ms"] = int((time.perf_counter() - started) * 1000)
                return result
        except Exception:  # noqa: BLE001 - silently fall back to RAG on failure
            pass

    try:
        # 1. Embed the question.
        question_vector = embeddings.embed_text(question)

        # 2. Retrieve the most relevant award chunks from Pinecone.
        matches = vectorstore.query(question_vector, top_k)
        result["retrieval_ms"] = int((time.perf_counter() - started) * 1000)
        result["matches_found"] = len(matches)

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

        # 4. Generate the grounded answer.
        llm_started = time.perf_counter()
        if not context:
            result["answer"] = "I could not find this in the award."
        else:
            result["answer"] = llm.generate_answer(question, context, history=history)
        result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)

    except Exception as exc:  # noqa: BLE001 - surfaced to the caller via result
        result["success"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        if not result["answer"]:
            result["answer"] = "Sorry, I could not process your question right now."

    result["total_ms"] = int((time.perf_counter() - started) * 1000)
    return result


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
            if looked_up:
                emp["base_hourly_rate"] = looked_up

    # Apply the stored public holidays so a shift worked on one gets the
    # right penalty loading without the user having to list the dates.
    _inject_public_holidays(payload)

    # Validate required fields manually so we can give a clear message.
    missing = _find_missing_required(payload)

    if missing:
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

    # Explain the result in plain English (deterministic fallback if the LLM
    # explanation fails — the figures are already computed and verified).
    try:
        result["answer"] = llm.explain_calculation(question, calc)
    except Exception:  # noqa: BLE001
        result["answer"] = _format_calculation(calc)
    result["llm_ms"] = int((time.perf_counter() - llm_started) * 1000)
    return True


def _inject_calc_defaults(payload: dict, question: str = ""):
    """Fill in sensible defaults for optional SCHADS fields."""
    emp = payload.setdefault("employee", {})
    if not isinstance(emp, dict):
        payload["employee"] = emp = {}
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
        kw in q_lower for kw in ("sleepover", "sleep over", "slept over", "overnight")
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
