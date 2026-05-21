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
import re
import time
from typing import Callable

from django.conf import settings

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
- A shift running past midnight is ONE shift with ONE segment whose end time
  is on the next day.
- REQUIRED fields (if any are missing, list them in "missing"):
    • employment_type (CASUAL or PERMANENT)
    • at least one shift with start and end ISO-8601 datetimes
- base_hourly_rate is PREFERRED but OPTIONAL when the user gives:
    • stream + classification_level + pay_point  (rate is looked up automatically)
  Only list "hourly rate" in "missing" if neither the rate nor the
  classification details above are provided.
- OPTIONAL fields — do NOT list these in "missing"; just default them:
    • stream, classification_level, pay_point, disability_services_work,
      is_sleepover, km, had_break, and every tenant_config boolean.
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


class LLMError(RuntimeError):
    pass


def _get_provider():
    return getattr(settings, "LLM", {}).get("PROVIDER", "ollama")


def _cfg():
    return getattr(settings, "LLM", {})


def _dispatch(user_message, system_prompt, json_mode=False, max_tokens=512, history=None):
    """Route a chat request to the configured provider.

    ``history`` is an optional list of prior ``{"role", "content"}`` turns —
    the conversation memory replayed so the user need not repeat context.
    """
    provider = _get_provider()
    if provider == "ollama":
        return _ollama_chat(user_message, system_prompt, json_mode, max_tokens, history)
    elif provider == "openai":
        return _openai_chat(user_message, system_prompt, json_mode, max_tokens, history)
    elif provider == "groq":
        return _groq_chat(user_message, system_prompt, json_mode, max_tokens, history)
    elif provider == "gemini":
        return _gemini_chat(user_message, system_prompt, json_mode, max_tokens, history)
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


@traceable(run_type="llm", name="llm-extract-calculation")
def extract_calculation(question, today, history=None):
    """Turn a natural-language pay question into a SCHADS engine payload.

    Returns the parsed dict ``{"is_calculation", "missing", "payload"}``.
    Prior conversation turns are passed so the user need not repeat details.
    """
    user_message = (
        f"Current date: {today}\n\n"
        f"User question:\n{question}"
    )
    raw = _dispatch(
        user_message, EXTRACTION_SYSTEM_PROMPT, json_mode=True, max_tokens=900,
        history=history,
    )
    return _parse_json(raw)


@traceable(run_type="llm", name="llm-explain-calculation")
def explain_calculation(question, calc_result):
    """Explain a SCHADS engine result in plain English."""
    user_message = (
        f"User question:\n{question}\n\n"
        f"SCHADS engine result (JSON):\n{json.dumps(calc_result, indent=2)}\n\n"
        f"Explain this result to the employee."
    )
    return _dispatch(user_message, EXPLANATION_SYSTEM_PROMPT, max_tokens=700)


def _ollama_chat(user_message, system_prompt, json_mode=False, max_tokens=256, history=None):
    import requests
    cfg = _cfg()
    timeout = cfg.get("TIMEOUT", 60)
    body = {
        "model": getattr(settings, "OLLAMA", {}).get("CHAT_MODEL", "qwen2.5:7b-instruct-q4_K_M"),
        "messages": _build_messages(system_prompt, user_message, history),
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": 8192},
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


def _openai_chat(user_message, system_prompt, json_mode=False, max_tokens=512, history=None):
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
        temperature=0.2,
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


def _groq_chat(user_message, system_prompt, json_mode=False, max_tokens=512, history=None):
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
        temperature=0.2,
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


def _gemini_chat(user_message, system_prompt, json_mode=False, max_tokens=512, history=None):
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
        temperature=0.2,
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
