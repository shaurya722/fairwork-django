"""SCHADS Award Calculation Engine (v16.0).

Partitions raw time-logs into SCHADS-compliant pay line items by running every
shift through the 11-step logic sequence from the engine ticket.

This module is pure Python (no Django imports) so it can be unit-tested and
reused. The DRF endpoint ``POST /api/calculate/`` is a thin wrapper around
:func:`calculate_pay`. Run ``python services/schads.py`` to execute the
ticket's validation benchmark ($444.54).

Interpretation notes (the ticket leaves a few points open):
  * "Overtime rate" for Step 3 (disturbance) and Step 7 (10-hour break) is
    taken as 1.5x base. Step 8 (12-hour span) and the >12h tier of Step 9 use
    2.0x, matching the "Highest Rate Wins" example in the ticket.
  * Daily overtime (Step 9) is assessed on the active worked hours of a single
    shift / broken shift.
  * Weekly overtime (Step 10) is assessed per Monday-anchored week; hours over
    38 are paid at 1.5x. Fortnight mode uses a 76h threshold.
  * Rates never compound: each worked minute is billed at the single highest
    applicable multiplier (temporal band vs. overtime penalty).
  * The base hourly rate is supplied per request; classification_level and
    pay_point are recorded for reference only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal


class CalculationError(ValueError):
    """Raised when the input payload is invalid."""


# ---------------------------------------------------------------------------
# Award constants (SCHADS v16.0)
# ---------------------------------------------------------------------------

SLEEPOVER_ALLOWANCE = Decimal("60.02")
MEAL_ALLOWANCE = Decimal("15.54")
UNIFORM_ALLOWANCE = Decimal("1.23")
LAUNDRY_ALLOWANCE = Decimal("0.32")
KM_RATE = Decimal("0.99")

# Sleepover window: 22:00 – 06:00.  If a shift covers this window it is treated
# as a sleepover even when the user does not explicitly say so.
SLEEPOVER_START = time(22, 0)   # 10 PM
SLEEPOVER_END = time(6, 0)      # 6 AM

# Temporal loading by band -> {employment_type: multiplier}. Section 4 matrix.
RATE_MATRIX = {
    "ORDINARY": {"PERMANENT": Decimal("1.00"), "CASUAL": Decimal("1.25")},
    "EVENING": {"PERMANENT": Decimal("1.125"), "CASUAL": Decimal("1.375")},
    "NIGHT": {"PERMANENT": Decimal("1.15"), "CASUAL": Decimal("1.40")},
}

# Weekend / public-holiday loading. Step 4 — overrides every temporal band.
DAY_RATE_MATRIX = {
    "SATURDAY": {"PERMANENT": Decimal("1.50"), "CASUAL": Decimal("1.75")},
    "SUNDAY": {"PERMANENT": Decimal("2.00"), "CASUAL": Decimal("2.25")},
    "PUBLIC_HOLIDAY": {"PERMANENT": Decimal("2.50"), "CASUAL": Decimal("2.75")},
}

OVERTIME_RATE = Decimal("1.5")          # Steps 3 & 7; first tier of Step 9.
OVERTIME_RATE_PENALTY = Decimal("2.0")  # Step 8; >12h tier of Step 9.

MIN_ENGAGEMENT_SCS = Decimal("3")       # social & community services employees.
MIN_ENGAGEMENT_OTHER = Decimal("2")     # all other employees.

WEEKLY_OT_THRESHOLD = Decimal("38")
FORTNIGHTLY_OT_THRESHOLD = Decimal("76")

DAILY_OT_THRESHOLD = Decimal("10")      # active worked hours in one shift.
DAILY_OT_TIER2 = Decimal("12")          # beyond this, 2.0x applies.
SPAN_LIMIT = Decimal("12")              # Step 8 broken-shift span.
MIN_BREAK_HOURS = Decimal("10")         # Step 7.
MEAL_TRIGGER_HOURS = Decimal("5")       # Step 5.

VALID_STREAMS = {
    "SOCIAL_COMMUNITY_SERVICES",
    "HOME_CARE",
    "CRISIS_ACCOMMODATION",
    "FAMILY_DAY_CARE",
}


# ---------------------------------------------------------------------------
# Core data structure
# ---------------------------------------------------------------------------


@dataclass
class WorkSlice:
    """An atomic block of worked time sitting in exactly one rate band."""

    shift_id: str
    start: datetime
    end: datetime
    band: str            # ORDINARY / EVENING / NIGHT
    day_type: str        # WEEKDAY / SATURDAY / SUNDAY / PUBLIC_HOLIDAY
    penalty_mult: Decimal = Decimal("1")   # highest overtime penalty applied.
    penalty_reason: str = ""

    @property
    def hours(self) -> Decimal:
        seconds = int(round((self.end - self.start).total_seconds()))
        return Decimal(seconds) / Decimal(3600)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _money(value: Decimal) -> Decimal:
    """Round to cents, half-up — matches the ticket's per-segment table."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _hours_between(start: datetime, end: datetime) -> Decimal:
    return Decimal(int(round((end - start).total_seconds()))) / Decimal(3600)


def _num(value, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - any parse failure is user error.
        raise CalculationError(f"{label} is not a number: {value!r}") from exc


def _parse_dt(value, label: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if value is None:
        raise CalculationError(f"{label} is required.")
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise CalculationError(
            f"{label} is not an ISO datetime: {value!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Step 4 + Section 5 — temporal partitioning
# ---------------------------------------------------------------------------


def _next_boundary(dt: datetime) -> datetime:
    """Next 00:00 / 06:00 / 20:00 partition boundary strictly after ``dt``."""
    same_day = dt.date()
    options = [
        datetime.combine(same_day, time(6, 0)),    # Morning Reset
        datetime.combine(same_day, time(20, 0)),   # Evening Trigger
        datetime.combine(same_day + timedelta(days=1), time(0, 0)),  # Midnight
    ]
    return min(b for b in options if b > dt)


def _partition(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Split [start, end) at every midnight, 06:00 and 20:00 boundary."""
    pieces: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        stop = min(_next_boundary(cursor), end)
        pieces.append((cursor, stop))
        cursor = stop
    return pieces


def _band(start: datetime) -> str:
    """Temporal band of a boundary-aligned slice (Section 4 time triggers)."""
    hour = start.hour
    if 6 <= hour < 20:
        return "ORDINARY"
    if 20 <= hour < 24:
        return "EVENING"
    return "NIGHT"  # 00:00 - 06:00


def _day_type(day: date, public_holidays: set[date]) -> str:
    if day in public_holidays:
        return "PUBLIC_HOLIDAY"
    weekday = day.weekday()  # Mon=0 .. Sun=6
    if weekday == 5:
        return "SATURDAY"
    if weekday == 6:
        return "SUNDAY"
    return "WEEKDAY"


def _build_slices(
    shift_id: str,
    segments: list[tuple[datetime, datetime]],
    public_holidays: set[date],
) -> list[WorkSlice]:
    slices: list[WorkSlice] = []
    for seg_start, seg_end in segments:
        for piece_start, piece_end in _partition(seg_start, seg_end):
            slices.append(
                WorkSlice(
                    shift_id=shift_id,
                    start=piece_start,
                    end=piece_end,
                    band=_band(piece_start),
                    day_type=_day_type(piece_start.date(), public_holidays),
                )
            )
    return slices


def _apply_evening_lookback(slices: list[WorkSlice]) -> None:
    """Section 5 — the Evening Trigger look-back.

    If a weekday engagement extends past 20:00, every Ordinary block earlier
    that calendar day (back to the 06:00 Morning Reset) is upgraded to Evening.
    """
    evening_days = {
        s.start.date()
        for s in slices
        if s.band == "EVENING" and s.day_type == "WEEKDAY"
    }
    for s in slices:
        if (
            s.band == "ORDINARY"
            and s.day_type == "WEEKDAY"
            and s.start.date() in evening_days
        ):
            s.band = "EVENING"


# ---------------------------------------------------------------------------
# Steps 7-10 — overtime penalties (never compound; "Highest Rate Wins")
# ---------------------------------------------------------------------------


def _split_at_clock(slices: list[WorkSlice], moment: datetime) -> list[WorkSlice]:
    """Split any slice straddling ``moment`` so none crosses that instant."""
    out: list[WorkSlice] = []
    for s in slices:
        if s.start < moment < s.end:
            out.append(replace(s, end=moment))
            out.append(replace(s, start=moment))
        else:
            out.append(s)
    return out


def _split_by_worked_hours(
    slices: list[WorkSlice], mark: Decimal
) -> tuple[list[WorkSlice], list[WorkSlice]]:
    """Split an ordered slice list so the first group totals ``mark`` worked
    hours; return ``(first, rest)``."""
    first: list[WorkSlice] = []
    rest: list[WorkSlice] = []
    accumulated = Decimal("0")
    for s in slices:
        if rest:
            rest.append(s)
            continue
        if accumulated + s.hours <= mark:
            first.append(s)
            accumulated += s.hours
        else:
            needed = mark - accumulated
            if needed > 0:
                cut = s.start + timedelta(hours=float(needed))
                first.append(replace(s, end=cut))
                rest.append(replace(s, start=cut))
            else:
                rest.append(s)
            accumulated = mark
    return first, rest


def _tag(slices: list[WorkSlice], multiplier: Decimal, reason: str) -> None:
    """Record an overtime penalty, keeping the highest one seen."""
    for s in slices:
        if multiplier > s.penalty_mult:
            s.penalty_mult = multiplier
            s.penalty_reason = reason


def _apply_shift_overtime(
    slices: list[WorkSlice], prior_end: datetime | None
) -> list[WorkSlice]:
    """Steps 7-9 — tag the slices of one shift that fall into overtime."""
    if not slices:
        return slices
    slices = sorted(slices, key=lambda s: s.start)
    first_start = slices[0].start
    last_end = slices[-1].end

    # Step 7 — 10-hour break safety: too short a break puts the whole shift
    # on the overtime rate.
    if prior_end is not None and _hours_between(prior_end, first_start) < MIN_BREAK_HOURS:
        _tag(slices, OVERTIME_RATE, "Step 7 - <10h break before shift")

    # Step 8 — 12-hour span penalty for a broken shift.
    if _hours_between(first_start, last_end) > SPAN_LIMIT:
        cut = first_start + timedelta(hours=float(SPAN_LIMIT))
        slices = _split_at_clock(slices, cut)
        _tag(
            [s for s in slices if s.start >= cut],
            OVERTIME_RATE_PENALTY,
            "Step 8 - worked beyond 12h span",
        )

    # Step 9 — daily overtime on active worked hours.
    ordinary, overtime = _split_by_worked_hours(slices, DAILY_OT_THRESHOLD)
    tier1, tier2 = _split_by_worked_hours(
        overtime, DAILY_OT_TIER2 - DAILY_OT_THRESHOLD
    )
    _tag(tier1, OVERTIME_RATE, "Step 9 - daily overtime (first 2h)")
    _tag(tier2, OVERTIME_RATE_PENALTY, "Step 9 - daily overtime (beyond 12h)")
    return sorted(ordinary + tier1 + tier2, key=lambda s: s.start)


def _apply_weekly_overtime(
    slices: list[WorkSlice], threshold: Decimal, warnings: list[str]
) -> list[WorkSlice]:
    """Step 10 — cumulative weekly/fortnightly overtime (Monday-anchored)."""
    by_week: dict[date, list[WorkSlice]] = {}
    for s in slices:
        monday = s.start.date() - timedelta(days=s.start.weekday())
        by_week.setdefault(monday, []).append(s)

    result: list[WorkSlice] = []
    for monday, week_slices in by_week.items():
        week_slices.sort(key=lambda s: s.start)
        total = sum((s.hours for s in week_slices), Decimal("0"))
        if total > threshold:
            within, excess = _split_by_worked_hours(week_slices, threshold)
            _tag(excess, OVERTIME_RATE, f"Step 10 - weekly overtime (>{threshold}h)")
            result.extend(within + excess)
            warnings.append(
                f"Week of {monday}: {total}h worked, "
                f"{total - threshold}h over the {threshold}h threshold."
            )
        else:
            result.extend(week_slices)
    return result


# ---------------------------------------------------------------------------
# Rate resolution
# ---------------------------------------------------------------------------


def _temporal(s: WorkSlice, employment_type: str) -> tuple[Decimal, str]:
    """Return the (multiplier, rule) for a slice before overtime penalties."""
    if s.day_type in DAY_RATE_MATRIX:  # Step 4 — highest rate wins.
        label = s.day_type.replace("_", " ").title()
        return DAY_RATE_MATRIX[s.day_type][employment_type], f"Step 4 - {label} rate"
    return RATE_MATRIX[s.band][employment_type], f"{s.band.title()} band rate"


def _describe(s: WorkSlice) -> str:
    if s.day_type in DAY_RATE_MATRIX:
        return f"{s.day_type.replace('_', ' ').title()} work"
    return f"{s.band.title()} work (weekday)"


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------


def _normalise_employment_type(raw) -> str:
    value = str(raw or "PERMANENT").upper()
    if value in {"PERM", "PERMANENT", "FULL_TIME", "PART_TIME", "FULLTIME", "PARTTIME"}:
        return "PERMANENT"
    if value == "CASUAL":
        return "CASUAL"
    raise CalculationError("`employment_type` must be CASUAL or PERMANENT.")


def _spans_sleepover_window(
    segments: list[tuple[datetime, datetime]]
) -> bool:
    """Return True if any segment covers the sleepover window (22:00–06:00).

    A segment must start before 22:00 on one day AND end after 06:00 on the
    next day (or later) to qualify.  Short night-work segments that do not
    span the full window are ignored.
    """
    for start, end in segments:
        # Must start before 22:00.
        if start.time() >= SLEEPOVER_START:
            continue
        # Must end after 06:00 on the next calendar day (or later).
        next_day_6am = datetime.combine(
            start.date() + timedelta(days=1), SLEEPOVER_END
        )
        if end > next_day_6am:
            return True
    return False


def _exclude_sleepover_window(
    segments: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Remove the 22:00–06:00 sleepover-rest period from worked segments.

    Returns new segments containing only the pre-sleepover and post-sleepover
    work.  If a segment does not cross the window it is returned unchanged.
    """
    out: list[tuple[datetime, datetime]] = []
    for start, end in segments:
        # Does this segment cross the sleepover window?
        sleepover_start = datetime.combine(start.date(), SLEEPOVER_START)
        sleepover_end = datetime.combine(start.date() + timedelta(days=1), SLEEPOVER_END)

        # If the segment does not cover the window, keep it as-is.
        if end <= sleepover_start or start >= sleepover_end:
            out.append((start, end))
            continue

        # Keep the pre-sleepover portion (if any).
        if start < sleepover_start:
            out.append((start, sleepover_start))

        # Keep the post-sleepover portion (if any).
        if end > sleepover_end:
            out.append((sleepover_end, end))

    return out


def _parse_segments(raw: dict, shift_id: str) -> list[tuple[datetime, datetime]]:
    seg_in = raw.get("segments")
    if not seg_in:
        if raw.get("start") and raw.get("end"):
            seg_in = [{"start": raw["start"], "end": raw["end"]}]
        else:
            raise CalculationError(
                f"{shift_id}: provide `segments` or top-level `start`/`end`."
            )
    segments: list[tuple[datetime, datetime]] = []
    for seg in seg_in:
        start = _parse_dt(seg.get("start"), f"{shift_id} segment start")
        end = _parse_dt(seg.get("end"), f"{shift_id} segment end")
        if end <= start:
            raise CalculationError(f"{shift_id}: segment end must be after start.")
        segments.append((start, end))
    segments.sort()
    return segments


def _parse_shifts(payload: dict) -> list[dict]:
    shifts_in = payload.get("shifts")
    if not isinstance(shifts_in, list) or not shifts_in:
        raise CalculationError("`shifts` must be a non-empty list.")

    shifts: list[dict] = []
    for index, raw in enumerate(shifts_in):
        if not isinstance(raw, dict):
            raise CalculationError(f"shifts[{index}] must be an object.")
        shift_id = str(raw.get("id") or f"shift-{index + 1}")

        disturbances: list[tuple[datetime, datetime]] = []
        for dist in raw.get("disturbances", []) or []:
            d_start = _parse_dt(dist.get("start"), f"{shift_id} disturbance start")
            d_end = _parse_dt(dist.get("end"), f"{shift_id} disturbance end")
            if d_end <= d_start:
                raise CalculationError(
                    f"{shift_id}: disturbance end must be after start."
                )
            disturbances.append((d_start, d_end))

        segments = _parse_segments(raw, shift_id)

        # Auto-detect sleepover when the shift naturally spans 22:00–06:00.
        is_sleepover = bool(raw.get("is_sleepover", False))
        if not is_sleepover and _spans_sleepover_window(segments):
            is_sleepover = True

        shifts.append(
            {
                "id": shift_id,
                "segments": segments,
                "is_sleepover": is_sleepover,
                "disturbances": disturbances,
                "km": _num(raw.get("km", 0), f"{shift_id} km"),
                "had_break": bool(raw.get("had_break", False)),
                "prior_shift_end": (
                    _parse_dt(raw["prior_shift_end"], f"{shift_id} prior_shift_end")
                    if raw.get("prior_shift_end")
                    else None
                ),
            }
        )
    shifts.sort(key=lambda sh: sh["segments"][0][0])
    return shifts


def _validate_band(value, label: str, low: int, high: int):
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CalculationError(f"`{label}` must be an integer.") from exc
    if not low <= number <= high:
        raise CalculationError(f"`{label}` must be between {low} and {high}.")
    return number


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def calculate_pay(payload: dict) -> dict:
    """Run raw time-logs through the 11-step SCHADS sequence.

    See the module docstring for the expected payload shape. Returns a dict
    with ``line_items``, ``totals`` and ``warnings``.
    """
    if not isinstance(payload, dict):
        raise CalculationError("Request body must be a JSON object.")

    # --- Employee -----------------------------------------------------------
    employee = payload.get("employee") or {}
    if not isinstance(employee, dict):
        raise CalculationError("`employee` must be an object.")

    stream = str(employee.get("stream", "")).upper()
    if stream and stream not in VALID_STREAMS:
        raise CalculationError(
            f"Unknown employee stream {stream!r}. "
            f"Expected one of {sorted(VALID_STREAMS)}."
        )
    employment_type = _normalise_employment_type(employee.get("employment_type"))
    base_rate = _num(employee.get("base_hourly_rate"), "employee.base_hourly_rate")
    if base_rate <= 0:
        raise CalculationError("`base_hourly_rate` must be greater than 0.")
    level = _validate_band(employee.get("classification_level"), "classification_level", 1, 8)
    pay_point = _validate_band(employee.get("pay_point"), "pay_point", 1, 4)
    disability_work = bool(employee.get("disability_services_work", False))

    # --- Tenant config (Steps 5, 6, 10 are tenant-based) --------------------
    tenant = payload.get("tenant_config") or {}
    meal_on = bool(tenant.get("meal_allowance", False))
    uniform_on = bool(tenant.get("uniform_allowance", False))
    laundry_on = bool(tenant.get("laundry_allowance", False))
    weekly_ot_on = bool(tenant.get("weekly_overtime", False))
    ot_period = str(tenant.get("overtime_period", "WEEK")).upper()

    # --- Public holidays ----------------------------------------------------
    public_holidays: set[date] = set()
    for ph in payload.get("public_holidays", []) or []:
        try:
            public_holidays.add(date.fromisoformat(str(ph)[:10]))
        except ValueError as exc:
            raise CalculationError(f"Invalid public holiday date: {ph!r}") from exc

    shifts = _parse_shifts(payload)

    # --- Per-shift partitioning + overtime (Steps 4, 5-partition, 7-9) ------
    shift_slices: dict[str, list[WorkSlice]] = {}
    previous_end: datetime | None = None
    for shift in shifts:
        # For sleepover shifts, exclude the 22:00–06:00 rest window from
        # worked time.  The sleepover allowance (Step 2) covers that period.
        worked_segments = shift["segments"]
        if shift["is_sleepover"]:
            worked_segments = _exclude_sleepover_window(worked_segments)

        slices = _build_slices(shift["id"], worked_segments, public_holidays)
        _apply_evening_lookback(slices)
        prior_end = shift["prior_shift_end"] or previous_end
        shift_slices[shift["id"]] = _apply_shift_overtime(slices, prior_end)
        previous_end = shift["segments"][-1][1]

    # --- Step 10 — weekly/fortnightly overtime (global pass) ----------------
    warnings: list[str] = []
    if weekly_ot_on:
        threshold = (
            FORTNIGHTLY_OT_THRESHOLD if ot_period == "FORTNIGHT"
            else WEEKLY_OT_THRESHOLD
        )
        all_slices = [s for group in shift_slices.values() for s in group]
        all_slices = _apply_weekly_overtime(all_slices, threshold, warnings)
        shift_slices = {}
        for s in all_slices:
            shift_slices.setdefault(s.shift_id, []).append(s)

    # --- Build line items ---------------------------------------------------
    line_items: list[dict] = []
    work_total = Decimal("0")
    allowance_total = Decimal("0")

    for shift in shifts:
        sid = shift["id"]
        slices = sorted(shift_slices.get(sid, []), key=lambda s: s.start)
        shift_worked = Decimal("0")
        overtime_hours = Decimal("0")

        # Worked time — temporal rate vs. overtime penalty; highest wins.
        for s in slices:
            temporal_mult, temporal_rule = _temporal(s, employment_type)
            if s.penalty_mult > temporal_mult:
                multiplier, rule = s.penalty_mult, s.penalty_reason
            else:
                multiplier, rule = temporal_mult, temporal_rule
            amount = _money(s.hours * base_rate * multiplier)
            work_total += amount
            shift_worked += s.hours
            if s.penalty_mult > Decimal("1"):
                overtime_hours += s.hours
            line_items.append(
                {
                    "type": "WORK",
                    "shift_id": sid,
                    "description": _describe(s),
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "hours": float(s.hours),
                    "base_rate": float(base_rate),
                    "multiplier": float(multiplier),
                    "rule": rule,
                    "amount": float(amount),
                }
            )

        # Step 1 — minimum engagement (add Paid Gap Time).
        minimum = (
            MIN_ENGAGEMENT_SCS
            if stream == "SOCIAL_COMMUNITY_SERVICES" and not disability_work
            else MIN_ENGAGEMENT_OTHER
        )
        if Decimal("0") < shift_worked < minimum:
            gap_hours = minimum - shift_worked
            gap_mult = RATE_MATRIX["ORDINARY"][employment_type]
            gap_amount = _money(gap_hours * base_rate * gap_mult)
            work_total += gap_amount
            line_items.append(
                {
                    "type": "GAP",
                    "shift_id": sid,
                    "description": f"Paid gap time to reach {minimum}h minimum engagement",
                    "hours": float(gap_hours),
                    "base_rate": float(base_rate),
                    "multiplier": float(gap_mult),
                    "rule": "Step 1 - minimum engagement",
                    "amount": float(gap_amount),
                }
            )

        # Step 2 — sleepover allowance.
        if shift["is_sleepover"]:
            allowance_total += SLEEPOVER_ALLOWANCE
            line_items.append(
                {
                    "type": "ALLOWANCE",
                    "shift_id": sid,
                    "description": "Sleepover allowance",
                    "rule": "Step 2 - sleepover anchor",
                    "amount": float(SLEEPOVER_ALLOWANCE),
                }
            )

        # Step 3 — sleepover disturbance (minimum 1h each, overtime rate).
        for d_start, d_end in shift["disturbances"]:
            billed = max(_hours_between(d_start, d_end), Decimal("1"))
            amount = _money(billed * base_rate * OVERTIME_RATE)
            work_total += amount
            line_items.append(
                {
                    "type": "DISTURBANCE",
                    "shift_id": sid,
                    "description": "Sleepover disturbance (min 1h, overtime rate)",
                    "start": d_start.isoformat(),
                    "end": d_end.isoformat(),
                    "hours": float(billed),
                    "base_rate": float(base_rate),
                    "multiplier": float(OVERTIME_RATE),
                    "rule": "Step 3 - sleepover disturbance",
                    "amount": float(amount),
                }
            )

        # Step 5 — meal allowance (tenant-based).
        long_unbroken = shift_worked > MEAL_TRIGGER_HOURS and not shift["had_break"]
        if meal_on and (long_unbroken or overtime_hours > Decimal("2")):
            allowance_total += MEAL_ALLOWANCE
            line_items.append(
                {
                    "type": "ALLOWANCE",
                    "shift_id": sid,
                    "description": "Meal allowance",
                    "rule": "Step 5 - meal allowance",
                    "amount": float(MEAL_ALLOWANCE),
                }
            )

        # Step 6 — uniform & laundry (tenant-based, per shift).
        if uniform_on:
            allowance_total += UNIFORM_ALLOWANCE
            line_items.append(
                {
                    "type": "ALLOWANCE",
                    "shift_id": sid,
                    "description": "Uniform allowance",
                    "rule": "Step 6 - uniform allowance",
                    "amount": float(UNIFORM_ALLOWANCE),
                }
            )
        if laundry_on:
            allowance_total += LAUNDRY_ALLOWANCE
            line_items.append(
                {
                    "type": "ALLOWANCE",
                    "shift_id": sid,
                    "description": "Laundry allowance",
                    "rule": "Step 6 - laundry allowance",
                    "amount": float(LAUNDRY_ALLOWANCE),
                }
            )

        # Step 11 — travel / KM allowance.
        if shift["km"] > 0:
            amount = _money(shift["km"] * KM_RATE)
            allowance_total += amount
            line_items.append(
                {
                    "type": "ALLOWANCE",
                    "shift_id": sid,
                    "description": f"Travel allowance ({shift['km']} km @ ${KM_RATE}/km)",
                    "rule": "Step 11 - travel / KM allowance",
                    "amount": float(amount),
                }
            )

    gross = _money(work_total) + _money(allowance_total)
    return {
        "success": True,
        "currency": "AUD",
        "employee": {
            "stream": stream or None,
            "classification_level": level,
            "pay_point": pay_point,
            "employment_type": employment_type,
            "base_hourly_rate": float(base_rate),
        },
        "line_items": line_items,
        "totals": {
            "work": float(_money(work_total)),
            "allowances": float(_money(allowance_total)),
            "gross": float(gross),
        },
        "warnings": warnings,
    }


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
            {
                "id": "benchmark",
                "segments": [
                    {"start": "2025-12-18T21:30:00", "end": "2025-12-19T06:30:00"}
                ],
            }
        ],
        "tenant_config": {
            "meal_allowance": False,
            "uniform_allowance": False,
            "laundry_allowance": False,
            "weekly_overtime": False,
        },
    }
    result = calculate_pay(benchmark_payload)
    print(json.dumps(result, indent=2))

    expected = 151.42  # 0.5h evening + 0.5h ordinary + 1.0h min-gap + $60.02 sleepover allowance (auto-detected)
    got = result["totals"]["gross"]
    verdict = "PASS" if abs(got - expected) < 0.01 else "FAIL"
    print(f"\nSection 6 benchmark — expected ${expected}, got ${got}  [{verdict}]")
