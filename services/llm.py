"""Answer generation + structured extraction via multiple LLM providers.

Supported providers (set LLM_PROVIDER in .env):
- ollama   (local, free)
- openai   (GPT-4o, GPT-4o-mini)
- groq     (Llama 3.1 70B, Mixtral – very fast)
- gemini   (Gemini 1.5 Flash/Pro)

Three jobs, all provider-agnostic via ``_dispatch``:
- ``generate_answer``      – grounded RAG answer from retrieved award context.
- ``extract_calculation``  – turn a pay question into a SCHADS engine payload.
- ``explain_calculation``  – explain the engine's result in plain English.
"""

import json
import logging
import re
import time
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(**kwargs):
        def decorator(fn):
            return fn
        return decorator


def _retry_on_5xx(func: Callable, max_retries: int = 2, base_delay: float = 0.5):
    """Retry a function on transient 5xx errors (502, 503, 504) with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            if status and 500 <= status < 600 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            raise
    return None  # unreachable


SYSTEM_PROMPT = """You are a helpful assistant for the Australian Fair Work \
award system. You answer questions about award clauses for employees and \
employers.

Rules you must follow:
- Answer ONLY using the award context provided in the user message.
- If the answer is not in the context, reply exactly: "I could not find this in the award."
- Always cite the clause number(s) you used, e.g. "(Clause 28.1)".
- Explain in plain, simple English.
- Never invent wage figures, rates, percentages or rules.
- Be concise and practical.
- The conversation may include earlier turns; use them to resolve follow-up questions."""


# Used when the strict grounded answer fails (no matching clause) but the
# question is a follow-up or a general support question. A SCHADS rate
# reference is baked in so the assistant can explain *why* a multiplier
# applied to an earlier calculation without inventing figures.
SUPPORTIVE_SYSTEM_PROMPT = """You are a friendly, supportive payroll assistant \
for the Australian SCHADS award (MA000100). The user is mid-conversation — \
the earlier turns are your memory of what was already calculated or discussed.

How to answer:
- Be helpful and conversational. Never reply with a blank refusal.
- For follow-up questions ("explain", "why", "break it down", "what about..."),
  answer using the earlier turns: re-explain the previous calculation, the
  hours, the multipliers and which SCHADS rule produced each one.
- You MAY use the SCHADS rate reference below — it is the authoritative engine
  rule set. Do not invent any other figures, and do not invent award clause
  numbers.
- If a question is outside SCHADS payroll, answer briefly and politely, then
  steer back to what you can help with (pay calculations and award rules).
- Keep it concise and plain-English.

SCHADS rate reference (the calculation engine's rules):
- Weekday Ordinary (06:00-20:00): Permanent x1.00, Casual x1.25.
- Weekday Evening (a block that finishes between 20:00 and 24:00):
  Permanent x1.125, Casual x1.375. The "Evening trigger" also upgrades earlier
  ordinary hours that day once the shift runs past 20:00.
- Weekday Night (00:00-06:00): Permanent x1.15, Casual x1.40.
- Saturday: Permanent x1.50, Casual x1.75 — overrides the time-of-day band.
- Sunday: Permanent x2.00, Casual x2.25 — overrides the time-of-day band.
- Public holiday: Permanent x2.50, Casual x2.75 — overrides everything.
- The day of the week is decided by the shift's date; weekend/public-holiday
  rates always win over Evening/Night/Ordinary ("Highest Rate Wins").
- Overtime penalties: 1.5x then 2.0x; rates never compound.
- Allowances: sleepover $60.02, meal $15.54, uniform $1.23, laundry $0.32,
  travel $0.99/km."""


EXTRACTION_SYSTEM_PROMPT = """You turn an Australian SCHADS-award pay question \
into JSON for a payroll calculator. Output a single JSON object, nothing else.

Schema:
{
  "is_calculation": boolean,
  "missing": [strings],
  "payload": {
    "employee": {
      "stream": "SOCIAL_COMMUNITY_SERVICES" | "HOME_CARE" | "CRISIS_ACCOMMODATION" | "FAMILY_DAY_CARE" | null,
      "classification_level": integer 1-8 or null,
      "pay_point": integer 1-4 or null,
      "employment_type": "CASUAL" | "PERMANENT",
      "base_hourly_rate": number,
      "disability_services_work": boolean
    },
    "shifts": [
      {
        "id": string,
        "segments": [{"start": ISO-8601 datetime, "end": ISO-8601 datetime}],
        "is_sleepover": boolean,
        "km": number,
        "had_break": boolean
      }
    ],
    "tenant_config": {
      "meal_allowance": boolean, "uniform_allowance": boolean,
      "laundry_allowance": boolean, "weekly_overtime": boolean,
      "overtime_period": "WEEK" | "FORTNIGHT"
    }
  }
}

Rules:
- is_calculation is true ONLY if the user asks to compute pay/earnings for
  specific worked time (one or more shifts with a start and an end). General
  questions such as "what is the Saturday penalty rate?" are NOT calculations:
  return {"is_calculation": false, "missing": [], "payload": null}.
- Every datetime MUST be full ISO-8601 (YYYY-MM-DDTHH:MM:SS). The current date
  is given in the user message; use the current year when a year is omitted.
- DATE RULE (critical — the day of week changes the pay rate):
    • If the user gives a date or weekday, use exactly that.
    • If the user gives NO date at all, use the current date from the user
      message for the shift. NEVER guess or pick a random date — guessing a
      Friday vs a Wednesday silently changes the penalty rates and the total.
    • The same question must always produce the same dates.
- A shift running past midnight is ONE shift with ONE segment whose end time
  is on the next day.
- REQUIRED fields (if any are missing, list them in "missing"):
    • employment_type (CASUAL or PERMANENT)
    • at least one shift with start and end ISO-8601 datetimes
- base_hourly_rate is PREFERRED but OPTIONAL when the user gives:
    • stream + classification_level + pay_point  (rate is looked up automatically)
  CRITICAL RULE: If the user supplies stream + classification_level + pay_point
  (even in casual wording like "homecare level 2 pay point 3"), you MUST NOT
  include "base_hourly_rate" or "hourly rate" in the top-level "missing" array.
  The system will automatically look up the current rate from the award wage
  tables. Only list hourly rate as missing when the user gave NONE of the three
  identifiers (no stream, no level, no pay point) AND no explicit rate.
- Stream mapping (map common words to the EXACT enum value):
    • "home care", "homecare", "aged care", "in-home", "home care employee"
      → "HOME_CARE"
    • "social and community services", "SCS", "disability support",
      "disability services", "community services"
      → "SOCIAL_COMMUNITY_SERVICES"
    • "crisis accommodation", "crisis", "crisis accommodation employee"
      → "CRISIS_ACCOMMODATION"
    • "family day care", "fdc", "family day care employee"
      → "FAMILY_DAY_CARE"
- classification_level & pay_point parsing:
    • "level 2, pay point 3" or "paypoint 3 pay level 2"
      → classification_level=2, pay_point=3
    • "L3 PP1" → classification_level=3, pay_point=1
    • The number after "level" or "L" is classification_level.
    • The number after "pay point", "paypoint" or "PP" is pay_point.
- is_sleepover detection (CRITICAL — read the user's words carefully):
    • Set to TRUE only if the user explicitly mentions: "sleepover", "sleep over",
      "overnight", "sleep-over shift", "sleepover allowance".
    • Set to FALSE if the user says: "no sleepover", "without sleepover",
      "not a sleepover", "regular shift", "normal shift", "day shift".
    • Set to FALSE (default) when sleepover is NOT mentioned at all.
    • NEVER assume sleepover=true unless the user explicitly says it.
- OPTIONAL fields — do NOT list these in "missing"; just default them:
    • stream, classification_level, pay_point, disability_services_work,
      km, had_break, and every tenant_config boolean.
- Default unknown booleans to false, unknown numbers to 0, unknown enums to
  null. Never invent an hourly rate.
- The conversation may include earlier turns. Reuse details the user already
  gave (hourly rate, employment type, stream, shift times) so they need not
  repeat them; the newest user message is the current request.
- Output JSON only."""


EXPLANATION_SYSTEM_PROMPT = """You are a SCHADS-award payroll assistant. You \
receive the user's question and the JSON output of a verified SCHADS \
calculation engine.

Write a clear plain-English explanation for the employee:
- Start with the gross total in AUD.
- List each line item: the hours, the multiplier, the dollar amount, and the
  SCHADS rule (from the line item's "rule" field).
- Mention any allowances and anything listed in "warnings".
- Use the engine's numbers EXACTLY — never recalculate or round differently.
- Keep it concise: a short intro line, then a bullet list."""


# The Shift Lifecycle Payload reasoning prompt. Drives ``generate_shift_calculation``
# (and the ``/api/shift-calc/`` endpoint). The model is required to emit a
# markdown reasoning block followed by a single JSON object matching the
# documented Pydantic schema — see services/shift_calculator.py for the
# response parser.
SHIFT_CALC_SYSTEM_PROMPT = """You are the definitive Backend Financial Reasoning Engine for an Australian NDIS Care Management Platform. Your purpose is to evaluate shift telemetry data against embedded compliance logic, retrieved RAG context (NDIS Pricing Arrangements), and the explicit SCHADS Award Rule Matrix to calculate precise worker payouts, client invoice amounts, and identify systemic compliance anomalies.

---

### 🧩 PART 1: COMPREHENSIVE INPUT PARAMETER SCHEMA
You will ingest a unified Shift Lifecycle Payload containing the following structures:

1. Shift Core Context:
   - start_time & end_time (ISO 8601 UTC strings)
   - break_duration_minutes (Integer)
   - postcode (4-digit string mapped to local territory state code and MMM tier)
   - item_number (NDIS support item code)
   - employment_type ("FULL_TIME" | "PART_TIME" | "CASUAL")
   - service_stream ("SOCIAL_COMMUNITY" | "HOME_CARE_DISABILITY")

2. Cumulative State Accumulators:
   - employee_weekly_hours_accumulator (Float, hours already worked in the current payroll cycle)
   - worker_daily_shift_matrix (Array of Objects representing other distinct shifts completed by this worker on the same localized calendar date)
   - laundry_allowance_weekly_accumulated_payout (Float, dollar value already disbursed this week)
   - uniform_allowance_weekly_accumulated_payout (Float, dollar value already disbursed this week)
   - first_aid_allowance_weekly_accumulated_payout (Float, dollar value already disbursed this week)

3. Operational Telemetry Triggers:
   - is_cancellation (Boolean)
   - is_sleepover (Boolean)
   - is_remote_work (Boolean)
   - sleepover_disturbances (Array of Objects: { "disturbance_start": String, "disturbance_end": String })
   - employee_profile_flags: { "is_designated_first_aid_officer": Boolean, "requires_personal_phone_usage": Boolean, "requires_uniform_laundry": Boolean, "provided_own_uniform": Boolean, "hire_date": String }
   - claimed_allowances_and_expenses: { "km_travel_units": Float, "meal_allowances_claimed": Integer, "hot_work_average_temp": Float, "out_of_pocket_reimbursements": Float }

---

### 📊 PART 2: THE MATHEMATICAL RULE MATRIX

#### SECTION A: BASE SHIFT LOADING COEFFICIENTS
Multipliers apply to the 'employee_base_rate'. Casual loadings must be handled ADDITIVELY to shift penalties (Base * [Penalty + Casual Loading]), NOT multiplicatively.

| Shift Windows & Geographies | FT / PT Multiplier | Casual Multiplier (Additive 25%) |
| :--- | :--- | :--- |
| **Weekday Ordinary (Mon–Fri, 6am–8pm)** | 1.00 | 1.25 |
| **Afternoon Shift (Finishes after 8pm, before midnight)**| 1.125 | 1.375 |
| **Night Shift (Finishes after midnight / starts before 6am)**| 1.15 | 1.40 |
| **Saturday Ordinary (All hours within 6am–8pm span)** | 1.50 | 1.75 |
| **Sunday Ordinary (All hours)** | 2.00 | 2.25 |
| **Public Holiday Ordinary (All hours)** | 2.50 | 2.75 |
| **Remote Work: Daytime** | 1.25 | 1.50 |
| **Remote Work: Evening Shift** | 1.375 | 1.625 |
| **Remote Work: Night Shift** | 1.40 | 1.65 |
| **Remote Work: Saturday (Within 6am-8pm Span)** | 1.75 | 2.00 |
| **Remote Work: Saturday (First 2 hrs outside span)** | 1.75 | 2.00 |
| **Remote Work: Saturday (After 2 hrs outside span)** | 1.75 | 2.00 |
| **Remote Work: Sunday** | 2.25 | 2.50 |
| **Remote Work: Public Holiday** | 2.75 | 3.00 |

#### SECTION B: OVERTIME COMPENSATION ENGINE
Overtime rates override standard ordinary loadings. Overtime rules apply if daily hours pass 10 or weekly hours pass 38.

| Overtime Condition | FT / PT Multiplier | Casual Multiplier |
| :--- | :--- | :--- |
| **Daily Shift > 10 Hours (First 2 Hours)** | 1.75 | 2.00 |
| **Daily Shift > 10 Hours (Beyond 2 Hours)** | 2.25 | 2.50 |
| **Weekday Overtime (First 3 hrs FT, First 2 hrs PT)** | 1.50 | 1.75 |
| **Weekday Overtime (After 3 hrs FT, After 2 hrs PT)** | 2.00 | 2.25 |
| **Public Holiday Overtime** | 2.50 | 2.75 |
| **Rest Period Breach (< 10-hour break between shifts)** | 2.00 | 2.25 |

#### SECTION C: ALLOWANCES & STATUTORY REIMBURSEMENTS
- **Broken Shift (1 Unpaid Break):** $20.82 flat payout per instance.
- **Broken Shift (2 Unpaid Breaks):** $27.56 flat payout per instance.
- **First Aid Allowance:** $20.46 weekly cap. If calculated hourly: $0.54 per hour up to the weekly cap.
- **Hot Work (40°C–46°C):** $0.61 per hour (Enforce only if hire_date is before 8 August 1991).
- **Hot Work (> 46°C):** $0.73 per hour (Enforce only if hire_date is before 8 August 1991).
- **Laundry Allowance (Company Uniform):** $0.32 per shift up to a maximum weekly ceiling of $1.49.
- **Laundry Allowance (Standard Clothing):** $0.32 per shift flat rate.
- **Meal Allowance:** $16.62 flat per claimed unit.
- **On-Call Allowance (Mon–Fri 24hr window):** $24.50 flat per active on-call assignment.
- **Sleepover Allowance:** $60.02 flat payment per validated 8-hour inactive period.
- **Uniform Allowance:** $1.23 per shift up to a maximum weekly ceiling of $6.24.
- **Vehicle (KM) Allowance:** Pay worker $0.92 per km via payroll. Bill client $0.97 per km via NDIS invoice (Dual-entry Margin Rule).
- **Special Clothing:** Exact pass-through value of out_of_pocket_reimbursements with 0% markup.

---

### 🧭 PART 3: DETERMINISTIC ALGORITHMIC PIPELINE

#### Step 1: Normalization & Structural Partitioning
1. Localize all UTC timestamps into the worksite timezone resolved via the input postcode.
2. If the shift crosses a calendar midnight boundary, segment the total duration into explicit daily lines before applying holiday or weekend calculations.
3. Validate minimum engagement rules: Verify if the daily segment duration meets the threshold:
   - If service_stream is "SOCIAL_COMMUNITY", minimum duration is 3 hours.
   - If service_stream is "HOME_CARE_DISABILITY", minimum duration is 2 hours.
   - OVERRIDE: If a holiday applies and employment_type is "CASUAL" or "PART_TIME", the minimum engagement duration automatically increases to 4 hours. If actual hours worked are fewer, top up the base calculation array to meet the mandatory hours floor.

#### Step 2: Sleepover State Machine Execution
If `is_sleepover` is TRUE:
1. Enforce a mandatory 8-hour inactive segment. Allocate the flat $60.02 `sleepover_allowance_payout`. Ordinary shift hours flanking this 8-hour block are evaluated via standard Section A rates.
2. Evaluate `sleepover_disturbances`: Every disturbance entry maps to an immediate 2.0x overtime multiplier.
3. Apply Minimum Disturbance Floor: If cumulative disturbance duration is > 0 and <= 60 minutes, pay out exactly 1.0 hour at 2.0x. If cumulative disturbances exceed 1.5 hours total, terminate the sleepover construct completely. Convert all 8 inactive hours into an active night shift configuration paid at baseline loading parameters.
4. Enforce 24-Hour Active Duty Cap: Total active hours flanking the sleepover cannot exceed 8 hours. If violated, flag a data integrity warning.

#### Step 3: Multi-Pass Broken Shift & Span Tracker
1. Scan `worker_daily_shift_matrix`. If discrete shifts exist on the same localized calendar day separated by unpaid intervals, identify the broken shift type:
   - If 1 unpaid gap exists, assign the $20.82 allowance.
   - If 2 unpaid gaps exist, assign the $27.56 allowance. If gaps > 2, trigger a calculation error flag.
2. Span Watchdog Rule: Measure the time delta between the start of the earliest shift and the end of the final shift for that day. If this entire elapsed span exceeds 12 hours, convert every minute worked past the 12th hour into a 2.0x (or 2.25x for casuals) penalty rate override.

#### Step 4: Allowance Ceiling Capping Logic
Evaluate profile flags and apply dynamic limits against weekly accumulators:
- If `requires_uniform_laundry` is TRUE, calculate the shift allowance ($0.32). If `laundry_allowance_weekly_accumulated_payout` + $0.32 > $1.49, adjust the payout down to match the remaining headroom.
- Apply identical tracking for the Uniform Allowance against its weekly ceiling ($6.24) and the First Aid Allowance against its weekly ceiling ($20.46).

#### Step 5: Dual-Entry Invoice & Payroll Matrix Compilation
Execute the financial compilation step:
- `calculated_employee_payout` = (Ordinary Hours * Active Loadings) + (Overtime Hours * Multipliers) + Allowances + Reimbursements.
- `billable_client_total` = (Active Shift Hours * Resolved NDIS Price Cap) + (km_travel_units * $0.97) + Billable Out-of-Pocket Expenses.
- `gross_profit_margin` = ((billable_client_total - calculated_employee_payout) / billable_client_total) * 100.

---

### 🚫 PART 4: STRICT OUTPUT CONSTRAINT
You must output your internal calculation steps step-by-step inside a markdown block, followed by the final result wrapped in a single, well-formed JSON block matching the Pydantic schema below. Do not include any conversational prose outside the JSON wrapper.

{
  "shift_id": "string (uuid)",
  "compliance_check": {
    "minimum_engagement_met": true,
    "rest_period_breached": false,
    "broken_shift_span_exceeded_12h": false,
    "sleepover_voided_by_disturbances": false
  },
  "calculated_employee_payout": 0.00,
  "billable_client_total": 0.00,
  "gross_profit_margin": 0.00,
  "breakdown": {
    "ordinary_hours": 0.00,
    "overtime_hours": 0.00,
    "allowance_payouts": {
      "km_travel": 0.00,
      "broken_shift": 0.00,
      "first_aid": 0.00,
      "laundry": 0.00,
      "uniform": 0.00,
      "meal": 0.00,
      "on_call": 0.00,
      "sleepover": 0.00,
      "hot_work": 0.00
    },
    "reimbursements": 0.00
  },
  "quick_actions": [
    {
      "action_id": "string",
      "title": "string",
      "description": "string",
      "target_endpoint": "string",
      "payload_override": {}
    }
  ]
}"""


class LLMError(RuntimeError):
    pass


def _get_provider():
    return getattr(settings, "LLM", {}).get("PROVIDER", "ollama")


def _cfg():
    return getattr(settings, "LLM", {})


def _dispatch(user_message, system_prompt, json_mode=False, max_tokens=512,
              history=None, temperature=0.2):
    """Route a chat request to the configured provider.

    ``history`` is an optional list of prior ``{"role", "content"}`` turns —
    the conversation memory replayed so the user need not repeat context.

    ``temperature`` controls sampling: pass 0.0 for jobs that must be
    deterministic (calculation extraction, result explanation) so the same
    question always yields the same answer.
    """
    provider = _get_provider()
    if provider == "ollama":
        return _ollama_chat(user_message, system_prompt, json_mode, max_tokens, history, temperature)
    elif provider == "openai":
        return _openai_chat(user_message, system_prompt, json_mode, max_tokens, history, temperature)
    elif provider == "groq":
        return _groq_chat(user_message, system_prompt, json_mode, max_tokens, history, temperature)
    elif provider == "gemini":
        return _gemini_chat(user_message, system_prompt, json_mode, max_tokens, history, temperature)
    else:
        raise LLMError(f"Unknown LLM_PROVIDER: {provider}")


def _build_messages(system_prompt, user_message, history):
    """Assemble an OpenAI-style messages list: system, prior turns, new user."""
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _parse_json(text):
    """Parse a JSON object from a model response, tolerating code fences."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise LLMError("The model did not return valid JSON.")


@traceable(run_type="llm", name="llm-chat")
def generate_answer(question, context, history=None):
    """Generate a grounded answer from the retrieved award context."""
    user_message = (
        f"Award context:\n\"\"\"\n{context}\n\"\"\"\n\n"
        f"Question: {question}\n\n"
        f"Answer using only the context above and cite the clause numbers."
    )
    return _dispatch(user_message, SYSTEM_PROMPT, max_tokens=512, history=history)


NDIS_SYSTEM_PROMPT = """You are a specialist assistant for the NDIS Pricing \
Arrangements and Price Limits document published by the National Disability \
Insurance Agency (NDIA).

Rules you must follow:
- Answer ONLY using the NDIS context provided in the user message.
- If the answer is not in the context, reply exactly: "I could not find this in the NDIS pricing document."
- Always cite the section number and page when available, e.g. "(Section 2.4, p. 18)".
- The context will tell you which document year/version the user is asking \
about. If the user names a different year, say which year the answer is from.
- Explain in plain, simple English.
- Never invent prices, line items, support categories or rules.
- Be concise and practical.
- The conversation may include earlier turns; use them to resolve follow-ups."""


_NDIS_NO_ANSWER = "I could not find this in the NDIS pricing document."


@traceable(run_type="llm", name="llm-ndis-chat")
def generate_ndis_answer(question, context, history=None, document_label=""):
    """Generate a grounded answer from retrieved NDIS pricing context.

    ``document_label`` is shown to the model so it knows which year/version of
    the NDIS pricing arrangements the context comes from — important when a
    user asks "what changed this year?".
    """
    header = (
        f"NDIS document: {document_label}\n\n" if document_label else ""
    )
    user_message = (
        f"{header}NDIS context:\n\"\"\"\n{context}\n\"\"\"\n\n"
        f"Question: {question}\n\n"
        f"Answer using only the NDIS context above. Cite the section number "
        f"(and page where available)."
    )
    return _dispatch(user_message, NDIS_SYSTEM_PROMPT, max_tokens=600, history=history)


def is_ndis_refusal(answer: str) -> bool:
    """True if the NDIS grounded answer is the canned not-found reply."""
    return (answer or "").strip().lower().startswith(
        _NDIS_NO_ANSWER.lower().rstrip(".")
    )


def _extract_last_json_object(text: str):
    """Pull the LAST balanced ``{...}`` object out of ``text`` and parse it.

    The shift-calc prompt asks the model for a markdown reasoning block
    followed by a JSON object. The JSON block is always the last balanced
    pair of braces, so we scan right-to-left, count brace depth, and json.loads
    the slice. Returns ``(reasoning_markdown, parsed_dict)``.
    """
    if not text:
        raise LLMError("The model returned an empty response.")

    end = text.rfind("}")
    if end == -1:
        raise LLMError("The model response did not contain a JSON object.")

    depth = 0
    start = -1
    for i in range(end, -1, -1):
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start == -1:
        raise LLMError("Could not find a balanced JSON object in the model response.")

    json_block = text[start : end + 1]
    try:
        parsed = json.loads(json_block)
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model returned invalid JSON: {exc}") from exc

    reasoning = text[:start].strip()
    return reasoning, parsed


@traceable(run_type="llm", name="llm-shift-calc")
def generate_shift_calculation(payload, employee_base_rate=None):
    """Run the Shift Lifecycle Payload through the NDIS reasoning prompt.

    ``payload`` is the Shift Lifecycle Payload (dict). ``employee_base_rate``
    is the worker's base hourly rate (optional — the model treats it as
    ``employee_base_rate`` from the matrix). Returns
    ``{"reasoning": str, "result": dict, "raw": str}``.

    Temperature is 0.0 because the same payload must always produce the same
    payout / invoice numbers — a few hundredths of a penalty multiplier change
    the gross.
    """
    body = {"shift_lifecycle_payload": payload}
    if employee_base_rate is not None:
        body["employee_base_rate"] = employee_base_rate

    user_message = (
        "Evaluate the following Shift Lifecycle Payload using the algorithmic "
        "pipeline (Steps 1-5). Show every numeric calculation step inside a "
        "markdown block titled '### Calculation Steps', then emit the final "
        "result as a single JSON object matching the Pydantic schema. The JSON "
        "must be the LAST content in your response.\n\n"
        f"INPUT:\n```json\n{json.dumps(body, indent=2)}\n```"
    )
    raw = _dispatch(
        user_message,
        SHIFT_CALC_SYSTEM_PROMPT,
        max_tokens=2200,
        temperature=0.0,
    )
    reasoning, parsed = _extract_last_json_object(raw)
    logger.info(
        "shift-calc: payout=%s invoice=%s margin=%s",
        parsed.get("calculated_employee_payout"),
        parsed.get("billable_client_total"),
        parsed.get("gross_profit_margin"),
    )
    return {"reasoning": reasoning, "result": parsed, "raw": raw}


@traceable(run_type="llm", name="llm-followup")
def generate_followup_answer(question, context="", history=None):
    """Answer a follow-up / general support question conversationally.

    Used when the strict grounded answer cannot help (no matching clause) but
    the conversation history — or general SCHADS knowledge — can. This is what
    keeps the bot supportive instead of dead-ending on
    "I could not find this in the award."
    """
    parts = []
    if context:
        parts.append(f"Award context that may help:\n\"\"\"\n{context}\n\"\"\"")
    parts.append(f"User question:\n{question}")
    parts.append(
        "Answer the user helpfully. If this is a follow-up about an earlier "
        "calculation, use the conversation above to explain it."
    )
    return _dispatch(
        "\n\n".join(parts), SUPPORTIVE_SYSTEM_PROMPT, max_tokens=600,
        history=history, temperature=0.3,
    )


@traceable(run_type="llm", name="llm-classify-question")
def classify_question(question):
    """Detect if a question is NDIS-related (pricing, support categories, etc.).
    
    Returns True if NDIS-related, False if Fair Work award / SCHADS / general.
    Uses a fast, deterministic keyword + pattern check to avoid an LLM call.
    """
    q_lower = question.lower()
    
    # Strong NDIS indicators
    ndis_keywords = [
        "ndis", "ndia", "national disability insurance",
        "support category", "support item", "price limit",
        "core support", "capacity building", "capital support",
        "plan management", "support coordination",
        "daily activities", "community participation",
        "transport", "consumables", "assistive technology",
        "home modification", "sil", "supported independent living",
    ]
    
    # Fair Work / SCHADS indicators (if these appear, it's NOT NDIS)
    award_keywords = [
        "schads", "fair work", "award", "clause",
        "penalty rate", "overtime", "casual loading",
        "shift", "hourly rate", "pay point", "classification level",
        "sleepover", "home care", "social community services",
        "public holiday", "weekend", "allowance",
    ]
    
    # Check award keywords first (higher priority)
    if any(kw in q_lower for kw in award_keywords):
        return False
    
    # Check NDIS keywords
    if any(kw in q_lower for kw in ndis_keywords):
        return True
    
    # Default to Fair Work (most common use case)
    return False


@traceable(run_type="llm", name="llm-extract-calculation")
def extract_calculation(question, today, history=None):
    """Turn a natural-language pay question into a SCHADS engine payload.

    Returns the parsed dict ``{"is_calculation", "missing", "payload"}``.
    Prior conversation turns are passed so the user need not repeat details.
    Runs at temperature 0.0 so the same question always extracts the same
    shift dates — guessing a date silently changes the penalty rate.
    """
    user_message = (
        f"Current date: {today}\n\n"
        f"User question:\n{question}"
    )
    raw = _dispatch(
        user_message, EXTRACTION_SYSTEM_PROMPT, json_mode=True, max_tokens=900,
        history=history, temperature=0.0,
    )
    parsed = _parse_json(raw)
    logger.info(
        "extraction: is_calculation=%s missing=%s",
        parsed.get("is_calculation"), parsed.get("missing"),
    )
    return parsed


@traceable(run_type="llm", name="llm-explain-calculation")
def explain_calculation(question, calc_result):
    """Explain a SCHADS engine result in plain English.

    Temperature 0.0 — the figures are already computed and verified, so the
    wording should not drift between identical results.
    """
    user_message = (
        f"User question:\n{question}\n\n"
        f"SCHADS engine result (JSON):\n{json.dumps(calc_result, indent=2)}\n\n"
        f"Explain this result to the employee."
    )
    return _dispatch(
        user_message, EXPLANATION_SYSTEM_PROMPT, max_tokens=700, temperature=0.0,
    )


def _ollama_chat(user_message, system_prompt, json_mode=False, max_tokens=256,
                 history=None, temperature=0.2):
    import requests
    cfg = _cfg()
    timeout = cfg.get("TIMEOUT", 60)
    body = {
        "model": getattr(settings, "OLLAMA", {}).get("CHAT_MODEL", "qwen2.5:7b-instruct-q4_K_M"),
        "messages": _build_messages(system_prompt, user_message, history),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192},
        "keep_alive": "5m",
    }
    if json_mode:
        body["format"] = "json"
    try:
        resp = requests.post(
            f"{getattr(settings, 'OLLAMA', {}).get('BASE_URL', 'http://localhost:11434')}/api/chat",
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.Timeout as exc:
        raise LLMError(f"Ollama timed out after {timeout}s.") from exc
    except Exception as exc:
        raise LLMError(f"Ollama error: {exc}") from exc
    answer = resp.json().get("message", {}).get("content", "").strip()
    if not answer:
        raise LLMError("Ollama returned empty answer.")
    return answer


def _openai_chat(user_message, system_prompt, json_mode=False, max_tokens=512,
                 history=None, temperature=0.2):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMError("openai package not installed. pip install openai") from exc

    cfg = _cfg()
    api_key = cfg.get("OPENAI_API_KEY")
    model = cfg.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    timeout = cfg.get("TIMEOUT", 60)
    if not api_key:
        raise LLMError("OPENAI_API_KEY is empty in .env")

    client = OpenAI(api_key=api_key, timeout=timeout)
    kwargs = dict(
        model=model,
        messages=_build_messages(system_prompt, user_message, history),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = _retry_on_5xx(lambda: client.chat.completions.create(**kwargs))
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            raise LLMError(f"OpenAI/Groq HTTP {status} error: {exc}") from exc
        raise LLMError(f"OpenAI error: {exc}") from exc
    return resp.choices[0].message.content.strip()


def _groq_chat(user_message, system_prompt, json_mode=False, max_tokens=512,
               history=None, temperature=0.2):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMError("openai package not installed. pip install openai") from exc

    cfg = _cfg()
    api_key = cfg.get("GROQ_API_KEY")
    model = cfg.get("GROQ_CHAT_MODEL", "llama-3.1-70b-versatile")
    timeout = cfg.get("TIMEOUT", 60)
    if not api_key:
        raise LLMError("GROQ_API_KEY is empty in .env")

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=timeout)
    kwargs = dict(
        model=model,
        messages=_build_messages(system_prompt, user_message, history),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = _retry_on_5xx(lambda: client.chat.completions.create(**kwargs))
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            raise LLMError(f"Groq HTTP {status} error: {exc}") from exc
        raise LLMError(f"Groq error: {exc}") from exc
    return resp.choices[0].message.content.strip()


def _gemini_chat(user_message, system_prompt, json_mode=False, max_tokens=512,
                 history=None, temperature=0.2):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise LLMError("google-genai not installed. pip install google-genai") from exc

    cfg = _cfg()
    api_key = cfg.get("GEMINI_API_KEY")
    model = cfg.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash")
    if not api_key:
        raise LLMError("GEMINI_API_KEY is empty in .env")

    config_kwargs = dict(
        system_instruction=system_prompt,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"

    contents = []
    for turn in history or []:
        role = turn.get("role")
        text = turn.get("content")
        if role in ("user", "assistant") and text:
            contents.append(
                {"role": "model" if role == "assistant" else "user",
                 "parts": [{"text": text}]}
            )
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            raise LLMError(f"Gemini HTTP {status} error: {exc}") from exc
        raise LLMError(f"Gemini error: {exc}") from exc
    return resp.text.strip() if resp.text else ""
