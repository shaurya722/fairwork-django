"""SCHADS pay-calculation adapter for the chatbot.

The actual calculation logic lives in :mod:`services.payroll_engine` — a
faithful Python port of the production Node.js payroll engine (see
``PAYROLL_SOURCE_CODE_FOR_PYTHON_PORT.md``). This module is a thin adapter:

  * :func:`calculate_pay` takes the chatbot's extracted payload, runs each
    shift through ``payroll_engine.process_shift``, and returns the
    ``line_items`` / ``totals`` / ``warnings`` shape the chat layer expects.

Keeping the engine separate means the chatbot's numbers stay in lock-step with
the production ``/payroll/calculate`` API. The public surface — ``calculate_pay``
and ``CalculationError`` — is unchanged, so ``services.rag`` needs no edits.

Run ``python services/schads.py`` to execute the ticket validation benchmark.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

try:  # normal import path (Django app)
    from . import payroll_engine as engine
    from .payroll_engine import CalculationError, EngineConfig, process_shift
except ImportError:  # running this file directly for the benchmark
    import payroll_engine as engine
    from payroll_engine import CalculationError, EngineConfig, process_shift

__all__ = ["calculate_pay", "CalculationError"]


# ---------------------------------------------------------------------------
# Input parsing helpers
# ---------------------------------------------------------------------------

VALID_STREAMS = {
    "SOCIAL_COMMUNITY_SERVICES",
    "HOME_CARE",
    "CRISIS_ACCOMMODATION",
    "FAMILY_DAY_CARE",
}


def _num(value, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationError(f"{label} is not a number: {value!r}") from exc


def _parse_dt(value, label: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if value is None:
        raise CalculationError(f"{label} is required.")
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise CalculationError(f"{label} is not an ISO datetime: {value!r}") from exc


def _normalise_employment_type(raw) -> str:
    """Return CASUAL or PERMANENT (the chatbot's two categories)."""
    value = str(raw or "PERMANENT").upper()
    if value in {"PERM", "PERMANENT", "FULL_TIME", "PART_TIME", "FULLTIME", "PARTTIME"}:
        return "PERMANENT"
    if value == "CASUAL":
        return "CASUAL"
    raise CalculationError("`employment_type` must be CASUAL or PERMANENT.")


def _engine_employment(employment_type: str) -> str:
    """Map the chatbot's CASUAL / PERMANENT to the engine's casual / fullTime."""
    return "casual" if employment_type == "CASUAL" else "fullTime"


# ---------------------------------------------------------------------------
# Line-item rendering
# ---------------------------------------------------------------------------

_SHIFT_LABELS = {
    "DAY": "Day / ordinary hours",
    "AFTERNOON": "Evening hours",
    "NIGHT": "Night hours",
    "SATURDAY": "Saturday",
    "SUNDAY": "Sunday",
    "PUBLIC_HOLIDAY": "Public holiday",
    "OVERTIME": "Overtime — level 1",
    "OVERTIME_L2": "Overtime — level 2",
    "SLEEPOVER": "Sleepover",
    "PAID_GAP_TIME": "Paid gap time",
}


def _rule_for(seg_pay) -> str:
    """A short, plain-English reason for the rate applied to a segment."""
    if seg_pay.seg.overtime_reason:
        return seg_pay.seg.overtime_reason
    shift_type = seg_pay.shift_type
    if shift_type == "SLEEPOVER":
        return ("Sleepover flat rate ($60.02)" if seg_pay.pay > 0
                else "Sleepover rest period (covered by the flat rate / unpaid)")
    if shift_type == "PAID_GAP_TIME":
        return "Minimum-engagement top-up (paid gap time)"
    if shift_type in ("SATURDAY", "SUNDAY", "PUBLIC_HOLIDAY"):
        return f"{_SHIFT_LABELS[shift_type]} penalty rate"
    if shift_type == "AFTERNOON":
        if seg_pay.seg.start.hour < 20:
            # Evening-trigger look-back: a weekday shift that runs past 8 PM
            # upgrades that day's earlier ordinary hours to the evening rate.
            return ("Evening rate — the shift extends past 8 PM, so all of "
                    "that day's hours are paid at the evening loading (8 PM "
                    "look-back rule)")
        return "Evening loading (hours worked between 8 PM and midnight)"
    if shift_type == "NIGHT":
        return "Night loading"
    if shift_type == "DAY":
        return "Ordinary rate"
    return shift_type or "Ordinary rate"


def _describe(seg_pay) -> str:
    label = _SHIFT_LABELS.get(seg_pay.shift_type, seg_pay.shift_type or "Work")
    day_type = seg_pay.seg.calendar_day_type
    if seg_pay.shift_type in ("DAY", "AFTERNOON", "NIGHT") and day_type == "WEEKDAY":
        return f"{label} (weekday)"
    return label


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def calculate_pay(payload: dict) -> dict:
    """Run the chatbot payload through the ported SCHADS engine.

    Expected payload (produced by ``llm.extract_calculation``)::

        {"employee": {"employment_type", "base_hourly_rate", "stream", ...},
         "shifts": [{"id", "segments": [{"start", "end"}], "is_sleepover",
                     "km", "disturbances", "prior_shift_end"}],
         "tenant_config": {"meal_allowance", "uniform_allowance", ...},
         "public_holidays": ["YYYY-MM-DD", ...]}

    Returns ``{"success", "currency", "employee", "line_items", "totals",
    "warnings"}`` — the shape ``services.rag`` and ``services.llm`` consume.
    """
    if not isinstance(payload, dict):
        raise CalculationError("Request body must be a JSON object.")

    # --- Employee -----------------------------------------------------------
    employee = payload.get("employee") or {}
    if not isinstance(employee, dict):
        raise CalculationError("`employee` must be an object.")

    stream = str(employee.get("stream") or "").upper()
    if stream and stream not in VALID_STREAMS:
        raise CalculationError(
            f"Unknown employee stream {stream!r}. "
            f"Expected one of {sorted(VALID_STREAMS)}."
        )
    employment_type = _normalise_employment_type(employee.get("employment_type"))
    base_rate = _num(employee.get("base_hourly_rate"), "employee.base_hourly_rate")
    if base_rate <= 0:
        raise CalculationError("`base_hourly_rate` must be greater than 0.")
    disability_work = bool(employee.get("disability_services_work", False))

    # --- Engine config (SCHADS defaults; minimum engagement varies) ---------
    config = EngineConfig()
    # Social & community services employees have a 3h minimum engagement;
    # everyone else 2h (and SCS doing disability work falls back to 2h).
    if stream == "SOCIAL_COMMUNITY_SERVICES" and not disability_work:
        config.min_engagement_minutes = 180.0

    for raw_holiday in payload.get("public_holidays", []) or []:
        try:
            config.holidays.add(date.fromisoformat(str(raw_holiday)[:10]))
        except ValueError as exc:
            raise CalculationError(f"Invalid public holiday date: {raw_holiday!r}") from exc

    # --- Tenant config — which allowances are switched on -------------------
    tenant = payload.get("tenant_config") or {}
    enabled = {"KM_TRAVEL", "SLEEPOVER"}
    if tenant.get("meal_allowance"):
        enabled.add("MEAL")
    if tenant.get("uniform_allowance"):
        enabled.add("UNIFORM")
    if tenant.get("laundry_allowance"):
        enabled.add("LAUNDRY")

    # --- Flatten shifts into individual engagements -------------------------
    # The engine processes one contiguous shift at a time, so each segment
    # becomes its own engagement (mirrors one Shift row in the Node model).
    engagements = _flatten_shifts(payload)
    if not engagements:
        raise CalculationError("`shifts` must contain at least one shift with times.")

    engine_employment = _engine_employment(employment_type)

    line_items: list[dict] = []
    warnings: list[str] = []
    work_total = 0.0
    allowance_total = 0.0

    previous_end: datetime | None = None
    weekly_hours: dict[date, float] = {}     # Monday -> worked hours
    daily_hours: dict[date, float] = {}      # calendar date -> worked hours

    for eng in engagements:
        start, end = eng["start"], eng["end"]
        monday = start.date() - timedelta(days=start.weekday())
        prior_periodic = weekly_hours.get(monday, 0.0)
        prior_daily = daily_hours.get(start.date(), 0.0)

        result = process_shift(
            start, end, config,
            employment_type=engine_employment,
            base_rate=base_rate,
            is_sleepover=eng["is_sleepover"],
            prev_shift_end=eng["prior_shift_end"] or previous_end,
            prior_daily_hours=prior_daily,
            prior_periodic_hours=prior_periodic,
            km_travelled=eng["km"],
            disturbances=eng["disturbances"],
            enabled_allowances=enabled,
        )

        worked = _render_engagement(
            eng["shift_id"], result, base_rate, line_items
        )
        work_total += result["work_pay"] + result["sleep_disturbances"]["total_pay"]
        allowance_total += sum(a["amount"] for a in result["allowances"])

        _collect_warnings(eng, result, warnings)

        weekly_hours[monday] = prior_periodic + worked
        daily_hours[start.date()] = prior_daily + worked
        previous_end = end

    work_total = engine._round2(work_total)
    allowance_total = engine._round2(allowance_total)
    gross = engine._round2(work_total + allowance_total)

    return {
        "success": True,
        "currency": "AUD",
        "employee": {
            "stream": stream or None,
            "classification_level": employee.get("classification_level"),
            "pay_point": employee.get("pay_point"),
            "employment_type": employment_type,
            "base_hourly_rate": base_rate,
        },
        "line_items": line_items,
        "totals": {
            "work": work_total,
            "allowances": allowance_total,
            "gross": gross,
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Adapter internals
# ---------------------------------------------------------------------------


def _flatten_shifts(payload: dict) -> list[dict]:
    """Turn the payload's shifts into a flat, time-ordered engagement list."""
    shifts_in = payload.get("shifts")
    if not isinstance(shifts_in, list) or not shifts_in:
        raise CalculationError("`shifts` must be a non-empty list.")

    engagements: list[dict] = []
    for index, raw in enumerate(shifts_in):
        if not isinstance(raw, dict):
            raise CalculationError(f"shifts[{index}] must be an object.")
        shift_id = str(raw.get("id") or f"shift-{index + 1}")

        seg_in = raw.get("segments")
        if not seg_in and raw.get("start") and raw.get("end"):
            seg_in = [{"start": raw["start"], "end": raw["end"]}]
        if not seg_in:
            raise CalculationError(
                f"{shift_id}: provide `segments` or top-level `start`/`end`."
            )

        disturbances = []
        for dist in raw.get("disturbances", []) or []:
            d_start = _parse_dt(dist.get("start"), f"{shift_id} disturbance start")
            d_end = _parse_dt(dist.get("end"), f"{shift_id} disturbance end")
            if d_end <= d_start:
                raise CalculationError(
                    f"{shift_id}: disturbance end must be after start."
                )
            disturbances.append((d_start, d_end))

        prior_end = (
            _parse_dt(raw["prior_shift_end"], f"{shift_id} prior_shift_end")
            if raw.get("prior_shift_end") else None
        )
        is_sleepover = bool(raw.get("is_sleepover", False))
        km = _num(raw.get("km", 0) or 0, f"{shift_id} km")

        for seg_index, seg in enumerate(seg_in):
            start = _parse_dt(seg.get("start"), f"{shift_id} segment start")
            end = _parse_dt(seg.get("end"), f"{shift_id} segment end")
            if end <= start:
                raise CalculationError(
                    f"{shift_id}: segment end must be after start."
                )
            engagements.append({
                "shift_id": shift_id,
                "start": start,
                "end": end,
                "is_sleepover": is_sleepover,
                # km / disturbances belong to the shift — apply once, to its
                # first segment, so a broken shift does not double-count them.
                "km": km if seg_index == 0 else 0.0,
                "disturbances": disturbances if seg_index == 0 else [],
                "prior_shift_end": prior_end if seg_index == 0 else None,
            })

    engagements.sort(key=lambda e: e["start"])
    return engagements


def _render_engagement(shift_id: str, result: dict, base_rate: float,
                       line_items: list[dict]) -> float:
    """Append this engagement's line items; return its worked hours."""
    worked_hours = 0.0
    for seg_pay in result["segment_payments"]:
        seg = seg_pay.seg
        hours = round(seg.hours, 4)
        if not seg.is_sleepover and not seg.is_gap:
            worked_hours += seg.hours

        # The unpaid leg of a sleepover that did get the flat rate adds noise;
        # skip a zero-pay sleepover segment unless it is the only thing here.
        if seg.is_sleepover and seg_pay.pay == 0 and result["sleepover_flat_rate_applied"]:
            continue

        line_items.append({
            "type": "WORK" if not seg.is_gap else "GAP",
            "shift_id": shift_id,
            "description": _describe(seg_pay),
            "start": seg.start.isoformat(),
            "end": seg.end.isoformat(),
            "hours": hours,
            "base_rate": base_rate,
            "multiplier": seg_pay.rate or None,
            "rule": _rule_for(seg_pay),
            "amount": seg_pay.pay,
        })

    disturbance = result["sleep_disturbances"]
    if disturbance["count"] > 0 and disturbance["total_pay"] > 0:
        line_items.append({
            "type": "DISTURBANCE",
            "shift_id": shift_id,
            "description": f"Sleep disturbance ×{disturbance['count']}",
            "hours": round(disturbance["total_charged_minutes"] / 60.0, 4),
            "base_rate": base_rate,
            "multiplier": None,
            "rule": "Disturbance — minimum 1h each, paid at the overtime rate",
            "amount": disturbance["total_pay"],
        })

    for allowance in result["allowances"]:
        line_items.append({
            "type": "ALLOWANCE",
            "shift_id": shift_id,
            "description": f"{allowance['type'].replace('_', ' ').title()} allowance",
            "multiplier": None,
            "rule": allowance.get("reason", ""),
            "amount": allowance["amount"],
        })
    return worked_hours


def _collect_warnings(eng: dict, result: dict, warnings: list[str]) -> None:
    """Surface anything the user should know about this engagement."""
    reasons = sorted({
        p.seg.overtime_reason for p in result["segment_payments"]
        if p.seg.overtime_reason
    })
    for reason in reasons:
        message = f"Overtime applied: {reason}."
        if message not in warnings:
            warnings.append(message)
    if eng["is_sleepover"] and not result["sleepover_flat_rate_applied"]:
        note = (
            "Sleepover did not qualify for the $60.02 flat rate (it needs 4+ "
            "hours of work either side of the sleep period); paid as an allowance."
        )
        if note not in warnings:
            warnings.append(note)


# ---------------------------------------------------------------------------
# Ticket validation benchmark — run `python services/schads.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    benchmark_payload = {
        "employee": {
            "stream": "HOME_CARE",
            "classification_level": 2,
            "pay_point": 1,
            "employment_type": "CASUAL",
            "base_hourly_rate": 35.67,
        },
        "shifts": [
            {"id": "benchmark",
             "segments": [{"start": "2025-12-18T21:30:00",
                           "end": "2025-12-19T06:30:00"}]}
        ],
    }
    result = calculate_pay(benchmark_payload)
    print(json.dumps(result, indent=2))

    expected = 444.54
    got = result["totals"]["gross"]
    verdict = "PASS" if abs(got - expected) < 0.01 else "FAIL"
    print(f"\nTicket Section 6 benchmark — expected ${expected}, got ${got}  [{verdict}]")
