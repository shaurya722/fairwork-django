"""Python port of the Node.js SCHADS payroll engine.

A faithful port of the engine in ``PAYROLL_SOURCE_CODE_FOR_PYTHON_PORT.md`` —
the same code that powers the production ``POST /payroll/calculate`` API. It is
ported so the chatbot's shift calculations match that engine.

Pipeline (``process_shift``), mirroring ``payrollEngine.ts``:
  1. build_shift_segments      — split a shift at definition boundaries;
                                 add Paid Gap Time for minimum engagement.
  2. resolve_all_segment_types — resolve each segment's type; apply daily /
                                 weekly / 12h-span overtime tiering (L1 1.5/1.75x,
                                 L2 2.0/2.25x); apply the 8 PM evening trigger.
  3. calculate_shift_pay       — multiply each segment by its rate; apply the
                                 sleepover flat rate ($60.02).
  4. sleep disturbances + allowances.

Timezone: the chatbot extracts naive wall-clock datetimes, so this port uses
the engine's ``timezone='UTC'`` (legacy) path — the hour of a datetime is taken
as the wall-clock hour the user meant. No DB: tenant config is the SCHADS
defaults below, overridable per call.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta


class CalculationError(ValueError):
    """Raised when the input to the engine is invalid."""


# ---------------------------------------------------------------------------
# SCHADS default tenant config (the engine's DB-backed config, as constants)
# ---------------------------------------------------------------------------

# Shift definitions: time windows + rate multipliers. Mirrors the rows the Node
# engine loads from `pricing.shift_definitions`. Values match the engine's
# built-in fallback multipliers (shiftTypeResolution.service `fallbacks`).
DEFAULT_SHIFT_DEFINITIONS = [
    {"type": "DAY",       "start": "06:00", "end": "20:00",
     "casual": 1.25,  "perm": 1.00},
    {"type": "AFTERNOON", "start": "20:00", "end": "24:00",
     "casual": 1.375, "perm": 1.125},
    {"type": "NIGHT",     "start": "00:00", "end": "06:00",
     "casual": 1.40,  "perm": 1.15},
    {"type": "SLEEPOVER", "start": "22:00", "end": "06:00",
     "casual": None,  "perm": None},
]

# Fallback multipliers for types without a time-window definition. Mirrors the
# `fallbacks` table in shiftTypeResolution.service.getShiftTypeMultiplier.
FALLBACK_MULTIPLIERS = {
    "DAY":            {"casual": 1.25, "perm": 1.00},
    "AFTERNOON":      {"casual": 1.375, "perm": 1.125},
    "NIGHT":          {"casual": 1.40, "perm": 1.15},
    "SATURDAY":       {"casual": 1.75, "perm": 1.50},
    "SUNDAY":         {"casual": 2.25, "perm": 2.00},
    "PUBLIC_HOLIDAY": {"casual": 2.75, "perm": 2.50},
    "OVERTIME":       {"casual": 1.75, "perm": 1.50},
    "OVERTIME_L2":    {"casual": 2.25, "perm": 2.00},
    "PAID_GAP_TIME":  {"casual": 1.25, "perm": 1.00},
    "SLEEPOVER":      {"casual": 1.40, "perm": 1.15},
}

SLEEPOVER_FLAT_RATE = 60.02            # payCalculation.service
DAILY_OT_THRESHOLD = 10                # rule OVERTIME_AFTER_HOURS
WEEKLY_OT_THRESHOLD = 38               # rule MAX_WEEKLY_HOURS
MIN_BREAK_HOURS = 10                   # rule MIN_BREAK_BETWEEN_SHIFTS
SPAN_THRESHOLD = 12                    # 12h broken-shift span (engine constant)

# Allowance amounts (rate + weekly cap). Mirrors the `pricing.allowances` rows.
DEFAULT_ALLOWANCES = {
    "MEAL":      {"rate": 15.54, "max_per_week": None},
    "LAUNDRY":   {"rate": 0.32,  "max_per_week": 999.0},
    "UNIFORM":   {"rate": 1.23,  "max_per_week": 999.0},
    "KM_TRAVEL": {"rate": 0.99,  "max_per_week": None},
    "SLEEPOVER": {"rate": SLEEPOVER_FLAT_RATE, "max_per_week": None},
}

ALL_ALLOWANCE_TYPES = ("MEAL", "LAUNDRY", "UNIFORM", "KM_TRAVEL", "SLEEPOVER")


@dataclass
class EngineConfig:
    """Tenant config for one calculation — SCHADS defaults unless overridden."""

    shift_definitions: list = field(
        default_factory=lambda: [dict(d) for d in DEFAULT_SHIFT_DEFINITIONS]
    )
    holidays: set = field(default_factory=set)          # set[date]
    allowances: dict = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_ALLOWANCES.items()}
    )
    min_engagement_minutes: float = 120.0               # 2h default; 3h for SCS
    daily_ot_threshold: float = DAILY_OT_THRESHOLD
    weekly_ot_threshold: float = WEEKLY_OT_THRESHOLD
    min_break_hours: float = MIN_BREAK_HOURS


# ---------------------------------------------------------------------------
# Core segment structure
# ---------------------------------------------------------------------------


@dataclass
class Seg:
    """One block of time within a shift, sitting in a single rate band."""

    start: datetime
    end: datetime
    calendar_day_type: str = "WEEKDAY"   # WEEKDAY / SATURDAY / SUNDAY / PUBLIC_HOLIDAY
    shift_type: str | None = None        # DAY / AFTERNOON / NIGHT / SLEEPOVER / OVERTIME...
    is_sleepover: bool = False
    is_gap: bool = False
    original_shift_start: datetime | None = None
    original_shift_end: datetime | None = None
    overtime_reason: str = ""
    sleepover_definition_end: datetime | None = None

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _round2(value) -> float:
    """Round to cents, half-up — matches the engine's roundCurrency."""
    return math.floor(float(value) * 100 + 0.5) / 100.0


def parse_time_to_minutes(text: str) -> float:
    """'HH:MM' / 'HH:MM:SS' -> minutes since midnight (timeUtils port)."""
    if not text:
        return 0.0
    parts = text.split(":")
    hours = int(parts[0]) if parts[0] else 0
    minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    seconds = int(parts[2]) if len(parts) > 2 and parts[2] else 0
    return hours * 60 + minutes + seconds / 60.0


def _js_day(dt: datetime) -> int:
    """Day of week, JS getUTCDay convention: Sunday=0 .. Saturday=6."""
    return (dt.weekday() + 1) % 7


def resolve_calendar_day_type(dt: datetime, holidays: set) -> str:
    """calendarUtils.resolveCalendarDayType — public holiday wins, then weekend."""
    if dt.date() in holidays:
        return "PUBLIC_HOLIDAY"
    day = _js_day(dt)
    if day == 0:
        return "SUNDAY"
    if day == 6:
        return "SATURDAY"
    return "WEEKDAY"


def _emp_key(employment_type: str) -> str:
    """'casual' -> 'casual'; everything else -> 'perm' (full/part time)."""
    return "casual" if str(employment_type).lower().startswith("casual") else "perm"


# ---------------------------------------------------------------------------
# Multiplier resolution — getShiftTypeMultiplier
# ---------------------------------------------------------------------------


def get_shift_type_multiplier(shift_type, config: EngineConfig, employment_type) -> float:
    key = _emp_key(employment_type)
    if shift_type == "PAID_GAP_TIME":
        day_def = next((d for d in config.shift_definitions if d["type"] == "DAY"), None)
        if day_def and day_def.get(key) is not None:
            return day_def[key]
    definition = next(
        (d for d in config.shift_definitions
         if (d["type"] or "").upper().strip() == shift_type),
        None,
    )
    if definition is not None and definition.get(key) is not None:
        return definition[key]
    fallback = FALLBACK_MULTIPLIERS.get(shift_type)
    if fallback:
        return fallback[key]
    raise CalculationError(f"No {employment_type} rate for shift type {shift_type!r}.")


# ---------------------------------------------------------------------------
# 1. Segmentation — splitByShiftDefinition / buildShiftSegments
# ---------------------------------------------------------------------------


def _def_matches(definition: dict, sec_in_day: float) -> bool:
    d_start = round(parse_time_to_minutes(definition["start"])) * 60
    d_end = round(parse_time_to_minutes(definition["end"])) * 60
    if d_end < d_start:                      # overnight window
        return sec_in_day >= d_start or sec_in_day < d_end
    return d_start <= sec_in_day < d_end


def _split_by_shift_definition(start, end, shift_definitions, allow_sleepover):
    """Port of splitByShiftDefinition (timezone='UTC' / legacy path)."""
    ref_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    total_seconds = (end - start).total_seconds()
    start_offset = (start - ref_start).total_seconds()
    end_offset = start_offset + total_seconds

    boundaries = [start_offset, end_offset]
    num_days_scan = math.ceil(end_offset / 86400) + 1

    sleepover_defs = (
        [] if not allow_sleepover
        else [d for d in shift_definitions
              if d["type"] == "SLEEPOVER" and d["start"] and d["end"]]
    )

    # Skip the compulsory midnight split if the shift overlaps a sleepover window.
    skip_midnight = False
    if sleepover_defs and allow_sleepover:
        for d in sleepover_defs:
            def_start = round(parse_time_to_minutes(d["start"])) * 60
            def_end_raw = round(parse_time_to_minutes(d["end"])) * 60
            def_end = def_end_raw + 86400 if def_end_raw < def_start else def_end_raw
            for day in range(-1, num_days_scan + 1):
                win_start = day * 86400 + def_start
                win_end = day * 86400 + def_end
                if not (end_offset <= win_start or start_offset >= win_end):
                    skip_midnight = True
                    break
            if skip_midnight:
                break

    # Sleepover-window boundaries.
    if sleepover_defs and allow_sleepover:
        for d in sleepover_defs:
            def_start = round(parse_time_to_minutes(d["start"])) * 60
            def_end_raw = round(parse_time_to_minutes(d["end"])) * 60
            def_end = def_end_raw + 86400 if def_end_raw < def_start else def_end_raw
            for day in range(-1, num_days_scan + 1):
                win_start = day * 86400 + def_start
                win_end = day * 86400 + def_end
                if win_end > start_offset and win_start < end_offset:
                    if start_offset < win_start < end_offset:
                        boundaries.append(win_start)
                    if start_offset < win_end < end_offset:
                        boundaries.append(win_end)

    # Compulsory midnight boundaries.
    if not skip_midnight:
        for day in range(num_days_scan):
            offset = day * 86400
            if start_offset < offset < end_offset:
                boundaries.append(offset)

    # Definition boundaries (06:00 / 20:00 / 00:00 etc).
    for day in range(num_days_scan):
        day_offset = day * 86400
        for d in shift_definitions:
            if not d["start"] or not d["end"]:
                continue
            def_start = round(parse_time_to_minutes(d["start"])) * 60
            def_end = round(parse_time_to_minutes(d["end"])) * 60
            abs_start = day_offset + def_start
            abs_end = day_offset + def_end
            if def_end < def_start:
                abs_end += 86400
            if start_offset < abs_start < end_offset:
                boundaries.append(abs_start)
            if start_offset < abs_end < end_offset:
                boundaries.append(abs_end)

    sorted_b = sorted(set(boundaries))
    result = []
    for i in range(len(sorted_b) - 1):
        seg_start_sec = sorted_b[i]
        seg_end_sec = sorted_b[i + 1]
        seg_start = ref_start + timedelta(seconds=seg_start_sec)
        seg_end = ref_start + timedelta(seconds=seg_end_sec)
        sec_in_day = seg_start_sec % 86400

        matching = [d for d in shift_definitions if _def_matches(d, sec_in_day)]
        if not allow_sleepover:
            matched = next((d for d in matching if d["type"] != "SLEEPOVER"),
                           matching[0] if matching else None)
        else:
            matched = next((d for d in matching if d["type"] == "SLEEPOVER"),
                           matching[0] if matching else None)
        result.append((seg_start, seg_end, matched))
    return result


def _minimum_engagement_gap(work_minutes: float, config: EngineConfig) -> float:
    """minimumEngagement.rule — minutes of Paid Gap Time needed."""
    minimum = config.min_engagement_minutes
    return max(0.0, minimum - work_minutes) if work_minutes < minimum else 0.0


def build_shift_segments(start, end, config: EngineConfig, *,
                         force_sleepover: bool, allow_sleepover: bool) -> list:
    """Port of buildShiftSegments — split + minimum engagement."""
    active = config.shift_definitions
    # When sleepover is not allowed, drop the SLEEPOVER definition.
    if not allow_sleepover and not force_sleepover:
        active = [d for d in active if d["type"] != "SLEEPOVER"]

    split = _split_by_shift_definition(
        start, end, active, allow_sleepover or force_sleepover
    )

    full: list[Seg] = []
    for seg_start, seg_end, matched in split:
        shift_type = matched["type"] if matched else None
        sleepover_def_end = None
        if shift_type == "SLEEPOVER" and matched and matched.get("end"):
            end_h, end_m = (int(x) for x in matched["end"].split(":")[:2])
            sleepover_def_end = seg_start.replace(
                hour=end_h % 24, minute=end_m, second=0, microsecond=0
            )
            if end_h <= seg_start.hour:
                sleepover_def_end += timedelta(days=1)
        full.append(Seg(
            start=seg_start,
            end=seg_end,
            calendar_day_type=resolve_calendar_day_type(seg_start, config.holidays),
            shift_type=shift_type,
            is_sleepover=(shift_type == "SLEEPOVER"),
            original_shift_start=start,
            original_shift_end=end,
            sleepover_definition_end=sleepover_def_end,
        ))

    # Minimum engagement — skipped entirely when the shift includes a sleepover.
    has_sleepover = any(s.is_sleepover for s in full)
    work_minutes = sum(
        s.duration_minutes for s in full
        if not s.is_sleepover and s.shift_type != "PAID_GAP_TIME"
    )
    remaining_gap = 0.0 if has_sleepover else _minimum_engagement_gap(work_minutes, config)

    # Group into engagements (work runs split by sleepover blocks).
    groups: list[list[Seg]] = []
    current: list[Seg] = []
    for seg in full:
        if seg.is_sleepover:
            if current:
                groups.append(current)
            groups.append([seg])
            current = []
        else:
            current.append(seg)
    if current:
        groups.append(current)

    final: list[Seg] = []
    for idx, group in enumerate(groups):
        if len(group) == 1 and group[0].is_sleepover:
            final.extend(group)
            continue
        final.extend(group)
        is_last_work_group = not any(
            not g[0].is_sleepover for g in groups[idx + 1:]
        )
        if is_last_work_group and remaining_gap > 0:
            prev = groups[idx - 1] if idx > 0 else None
            follows_sleepover = bool(prev and len(prev) == 1 and prev[0].is_sleepover)
            if not follows_sleepover:
                last = group[-1]
                gap_start = last.end
                gap_end = gap_start + timedelta(minutes=remaining_gap)
                final.append(Seg(
                    start=gap_start,
                    end=gap_end,
                    calendar_day_type=resolve_calendar_day_type(gap_start, config.holidays),
                    shift_type="PAID_GAP_TIME",
                    is_gap=True,
                    original_shift_start=start,
                    original_shift_end=end,
                ))
                remaining_gap = 0.0
    return final


# ---------------------------------------------------------------------------
# 2. Type resolution + overtime tiering — resolveAllSegmentTypes
# ---------------------------------------------------------------------------


def resolve_shift_type(seg: Seg, config: EngineConfig, *,
                       force_type=None, employment_type="casual") -> str:
    """Port of resolveShiftType — priority order from the engine."""
    is_holiday = seg.start.date() in config.holidays
    day = _js_day(seg.start)
    is_sun, is_sat = day == 0, day == 6
    is_sleepover = seg.is_sleepover or seg.shift_type == "SLEEPOVER"

    if is_holiday:                                          # 1. public holiday
        return "PUBLIC_HOLIDAY"
    if is_sun or is_sat:                                    # 2. weekend
        calendar_type = "SUNDAY" if is_sun else "SATURDAY"
        if force_type in ("OVERTIME", "OVERTIME_L2"):
            cal_mult = get_shift_type_multiplier(calendar_type, config, employment_type)
            ot_mult = get_shift_type_multiplier(force_type, config, employment_type)
            if ot_mult >= cal_mult:                         # overtime only if not lower
                return force_type
        return calendar_type
    if is_sleepover:                                        # 3. sleepover
        return "SLEEPOVER"
    if force_type:                                          # 4. forced overtime
        return force_type
    if seg.shift_type and seg.shift_type not in ("SLEEPOVER", "OVERTIME"):
        return seg.shift_type                               # 5. segmentation type
    # 6. time-of-day fallback.
    minutes = seg.start.hour * 60 + seg.start.minute
    priority = {"NIGHT": 3, "AFTERNOON": 2, "DAY": 1}
    for d in sorted(config.shift_definitions,
                    key=lambda x: priority.get(x["type"], 0), reverse=True):
        if not d["start"] or not d["end"]:
            continue
        d_start = round(parse_time_to_minutes(d["start"]))
        d_end = round(parse_time_to_minutes(d["end"]))
        if (d_end < d_start and (minutes >= d_start or minutes < d_end)) or \
           (d_end >= d_start and d_start <= minutes < d_end):
            return d["type"]
    return "DAY"


def _hours_in_24h_window(segments: list, window_start: datetime) -> float:
    """calculateHoursIn24HourWindow — non-sleepover hours in a rolling 24h."""
    window_end = window_start + timedelta(hours=24)
    total = 0.0
    for seg in segments:
        if seg.is_sleepover:
            continue
        s = max(seg.start, window_start)
        e = min(seg.end, window_end)
        if s < e:
            total += (e - s).total_seconds() / 3600.0
    return total


def resolve_all_segment_types(segments: list, config: EngineConfig, *,
                              prev_shift_end, first_shift_start_of_day,
                              prior_daily_hours, prior_periodic_hours,
                              periodic_threshold, employment_type) -> list:
    """Port of resolveAllSegmentTypes — overtime tiering + evening trigger."""
    sorted_segs = sorted(segments, key=lambda s: s.start)

    span_anchor = None
    sleepover_gap_hours = 0.0
    cumulative_hours = prior_daily_hours
    force_overtime = False

    is_first_shift_of_day = bool(
        first_shift_start_of_day is not None and sorted_segs
        and abs((sorted_segs[0].start - first_shift_start_of_day).total_seconds()) < 60
    )
    if (prev_shift_end is not None and sorted_segs and is_first_shift_of_day):
        break_hours = (sorted_segs[0].start - prev_shift_end).total_seconds() / 3600.0
        if break_hours < config.min_break_hours:
            force_overtime = True

    daily_work = config.daily_ot_threshold
    daily_l2 = daily_work + 2 if daily_work is not None else None
    periodic_work = periodic_threshold
    periodic_l2 = periodic_work + 2 if periodic_work is not None else None

    resolved: list[Seg] = []
    for segment in sorted_segs:
        if segment.is_sleepover:
            sleepover_gap_hours += segment.duration_minutes / 60.0
            resolved.append(replace(segment, shift_type="SLEEPOVER"))
            continue
        if span_anchor is None:
            span_anchor = segment.start

        seg_hours = segment.duration_minutes / 60.0
        worked_this_shift = cumulative_hours - prior_daily_hours
        cut_points: list[float] = []

        if daily_work is not None:
            t = daily_work - cumulative_hours
            if 0 < t < seg_hours:
                cut_points.append(t)
        if daily_l2 is not None:
            t = daily_l2 - cumulative_hours
            if 0 < t < seg_hours:
                cut_points.append(t)
        if periodic_work is not None:
            t = periodic_work - (prior_periodic_hours + worked_this_shift)
            if 0 < t < seg_hours:
                cut_points.append(t)
        if periodic_l2 is not None:
            t = periodic_l2 - (prior_periodic_hours + worked_this_shift)
            if 0 < t < seg_hours:
                cut_points.append(t)
        seg_span_start = (segment.start - span_anchor).total_seconds() / 3600.0 - sleepover_gap_hours
        t = SPAN_THRESHOLD - seg_span_start
        if 0 < t < seg_hours:
            cut_points.append(t)

        unique_cuts = sorted(set(cut_points))
        current_offset = 0.0
        for end_offset in unique_cuts + [seg_hours]:
            piece_hours = end_offset - current_offset
            if piece_hours <= 0.0001:
                current_offset = end_offset
                continue
            piece_start = segment.start + timedelta(hours=current_offset)
            piece_end = segment.start + timedelta(hours=end_offset)
            worked_now = cumulative_hours - prior_daily_hours

            piece_span_start = (
                (piece_start - span_anchor).total_seconds() / 3600.0 - sleepover_gap_hours
            )
            window_anchor = span_anchor or piece_start
            hours_24 = _hours_in_24h_window(
                [s for s in resolved if s.start <= piece_start], window_anchor
            ) + piece_hours

            is_daily_ot = daily_work is not None and (
                cumulative_hours >= daily_work or hours_24 > daily_work)
            is_daily_l2 = daily_l2 is not None and (
                cumulative_hours >= daily_l2 or hours_24 > daily_l2)
            is_periodic_ot = periodic_work is not None and (
                prior_periodic_hours + worked_now) >= periodic_work
            is_periodic_l2 = periodic_l2 is not None and (
                prior_periodic_hours + worked_now) >= periodic_l2
            is_span = piece_span_start >= SPAN_THRESHOLD

            resolved_type = None
            reason = ""
            if force_overtime or is_span or is_daily_ot or is_periodic_ot:
                if is_span:
                    reason = f"12-hour span exceeded (worked past {SPAN_THRESHOLD}h)"
                elif is_daily_l2:
                    reason = f"Daily overtime — level 2 (over {daily_l2}h)"
                elif is_periodic_l2:
                    reason = f"Weekly overtime — level 2 (over {periodic_l2}h)"
                elif is_daily_ot and is_periodic_ot:
                    reason = "Daily & weekly overtime"
                elif is_daily_ot:
                    reason = f"Daily overtime (over {daily_work}h in a 24h window)"
                elif is_periodic_ot:
                    reason = f"Weekly overtime (over {periodic_work}h)"
                else:
                    reason = f"Overtime — less than {config.min_break_hours}h break before shift"
                resolved_type = "OVERTIME_L2" if (is_daily_l2 or is_periodic_l2) else "OVERTIME"

            base_type = resolve_shift_type(
                replace(segment, start=piece_start, end=piece_end),
                config, force_type=resolved_type, employment_type=employment_type,
            )
            resolved.append(replace(
                segment, start=piece_start, end=piece_end, shift_type=base_type,
                calendar_day_type=resolve_calendar_day_type(piece_start, config.holidays),
                overtime_reason=reason,
            ))
            cumulative_hours += piece_hours
            current_offset = end_offset

    upgraded = apply_evening_trigger(resolved, config)
    return merge_segments(upgraded)


# ---------------------------------------------------------------------------
# Evening trigger (8 PM look-back) — eveningTrigger.rule
# ---------------------------------------------------------------------------


def apply_evening_trigger(segments: list, config: EngineConfig) -> list:
    """Port of applyEveningTriggerRule.

    On a weekday, if work for a calendar day continues past the Evening start
    (20:00), every preceding DAY block that day is upgraded to AFTERNOON.
    """
    afternoon = next((d for d in config.shift_definitions if d["type"] == "AFTERNOON"), None)
    day_def = next((d for d in config.shift_definitions if d["type"] == "DAY"), None)
    evening_hour = int(afternoon["start"].split(":")[0]) if afternoon else 20
    reset_hour = int(day_def["start"].split(":")[0]) if day_def else 6
    reset_min = int(day_def["start"].split(":")[1]) if day_def else 0

    # Group into engagements separated by reset points (local midnight / 06:00).
    engagements: list[list[Seg]] = []
    current: list[Seg] = []
    for idx, seg in enumerate(segments):
        is_reset = (
            (seg.start.hour == 0 and seg.start.minute == 0)
            or (seg.start.hour == reset_hour and seg.start.minute == reset_min)
        )
        if idx > 0 and is_reset:
            engagements.append(current)
            current = []
        current.append(seg)
    if current:
        engagements.append(current)

    for group in engagements:
        first = group[0]
        eng_day = first.start
        physical_end = first.original_shift_end or first.end
        same_day = eng_day.date() == physical_end.date()
        qualifies = (
            (not same_day and physical_end > eng_day)
            or (same_day and physical_end.hour >= evening_hour)
        )
        for seg in group:
            if qualifies and seg.shift_type == "DAY" and seg.calendar_day_type == "WEEKDAY":
                seg.shift_type = "AFTERNOON"
            elif not qualifies and seg.shift_type == "AFTERNOON" \
                    and seg.calendar_day_type == "WEEKDAY":
                seg.shift_type = "DAY"
    return segments


def merge_segments(segments: list) -> list:
    """Consolidate adjacent segments that share a shift type (segmentMerging)."""
    out: list[Seg] = []
    for seg in sorted(segments, key=lambda s: s.start):
        last = out[-1] if out else None
        if (last is not None and last.shift_type == seg.shift_type
                and last.is_sleepover == seg.is_sleepover
                and last.is_gap == seg.is_gap
                and last.end == seg.start
                and last.overtime_reason == seg.overtime_reason):
            last.end = seg.end
        else:
            out.append(replace(seg))
    return out


# ---------------------------------------------------------------------------
# 3. Pay calculation — payCalculation.service
# ---------------------------------------------------------------------------


@dataclass
class SegPay:
    seg: Seg
    shift_type: str
    rate: float
    pay: float


def _identify_sleepover_segments(segments: list):
    """identifySleepoverSegments — sleepover blocks + pre/post work."""
    ordered = sorted(segments, key=lambda s: s.start)
    sleepovers = [s for s in ordered if s.is_sleepover]
    if not sleepovers:
        return [], [], []
    first, last = sleepovers[0], sleepovers[-1]
    prefix = [s for s in ordered if not s.is_sleepover and s.end <= first.start]
    suffix = [s for s in ordered if not s.is_sleepover and s.start >= last.end]
    return sleepovers, prefix, suffix


def _qualifies_for_flat_rate(segments: list, physical_end: datetime) -> bool:
    """qualifiesForSleepoverFlatRate — 4h work either side + shift runs to the
    sleepover definition end."""
    sleepovers, prefix, suffix = _identify_sleepover_segments(segments)
    if not sleepovers:
        return False
    prefix_hours = sum(s.hours for s in prefix)
    suffix_hours = sum(s.hours for s in suffix)
    if prefix_hours < 4 and suffix_hours < 4:
        return False
    last = sleepovers[-1]
    required_end = last.sleepover_definition_end or last.end
    return physical_end >= required_end


def calculate_segment_pay(seg: Seg, base_rate: float, config: EngineConfig,
                          employment_type: str, override_pay=None) -> SegPay:
    shift_type = seg.shift_type or "DAY"
    if override_pay is not None:
        return SegPay(seg=seg, shift_type=shift_type, rate=0.0, pay=override_pay)
    multiplier = get_shift_type_multiplier(shift_type, config, employment_type)
    pay = _round2(seg.hours * base_rate * multiplier)
    return SegPay(seg=seg, shift_type=shift_type, rate=multiplier, pay=pay)


def calculate_shift_pay(segments: list, base_rate: float, config: EngineConfig,
                        employment_type: str) -> dict:
    """Port of calculateShiftPay — per-segment pay + sleepover flat rate."""
    ordered = sorted(segments, key=lambda s: s.start)
    sleepovers, prefix, suffix = _identify_sleepover_segments(ordered)
    has_sleepover = bool(sleepovers)

    physical_end = (
        ordered[-1].original_shift_end or ordered[-1].end if ordered else None
    )
    uses_flat_rate = has_sleepover and _qualifies_for_flat_rate(ordered, physical_end)
    flat_rate = config.allowances.get("SLEEPOVER", {}).get("rate") or SLEEPOVER_FLAT_RATE

    payments: list[SegPay] = []
    sleepover_flat_rate_applied = False

    if has_sleepover and not uses_flat_rate:
        for seg in prefix:
            payments.append(calculate_segment_pay(seg, base_rate, config, employment_type))
        for seg in sleepovers:                           # unpaid rest window
            payments.append(calculate_segment_pay(seg, base_rate, config,
                                                   employment_type, override_pay=0.0))
        for seg in suffix:
            payments.append(calculate_segment_pay(seg, base_rate, config, employment_type))
    elif uses_flat_rate:
        sleepover_flat_rate_applied = True
        for seg in prefix:
            payments.append(calculate_segment_pay(seg, base_rate, config, employment_type))
        payments.append(calculate_segment_pay(sleepovers[0], base_rate, config,
                                              employment_type, override_pay=flat_rate))
        for seg in sleepovers[1:]:
            payments.append(calculate_segment_pay(seg, base_rate, config,
                                                  employment_type, override_pay=0.0))
        for seg in suffix:
            payments.append(calculate_segment_pay(seg, base_rate, config, employment_type))
    else:
        for seg in ordered:
            payments.append(calculate_segment_pay(seg, base_rate, config, employment_type))

    total_pay = _round2(sum(p.pay for p in payments))
    overtime_pay = _round2(sum(
        p.pay for p in payments if p.shift_type in ("OVERTIME", "OVERTIME_L2")
    ))
    return {
        "segment_payments": payments,
        "base_pay": _round2(total_pay - overtime_pay),
        "overtime_pay": overtime_pay,
        "total_pay": total_pay,
        "sleepover_flat_rate_applied": sleepover_flat_rate_applied,
    }


# ---------------------------------------------------------------------------
# Allowances — allowanceCalculation.service
# ---------------------------------------------------------------------------


def calculate_allowances(segments: list, config: EngineConfig, *,
                         km_travelled: float, overtime_hours: float,
                         enabled: set) -> list:
    """Port of calculateAllowances (per-shift; weekly totals assumed 0)."""
    results = []

    if "LAUNDRY" in enabled:
        d = config.allowances.get("LAUNDRY")
        if d and d.get("rate") and d.get("max_per_week"):
            amount = _round2(max(0.0, min(d["rate"], d["max_per_week"])))
            results.append({"type": "LAUNDRY", "amount": amount,
                            "reason": "Per-shift laundry allowance"})

    if "UNIFORM" in enabled:
        d = config.allowances.get("UNIFORM")
        if d and d.get("rate") and d.get("max_per_week"):
            amount = _round2(max(0.0, min(d["rate"], d["max_per_week"])))
            results.append({"type": "UNIFORM", "amount": amount,
                            "reason": "Per-shift uniform allowance"})

    if "MEAL" in enabled:
        work_minutes = sum(s.duration_minutes for s in segments if not s.is_sleepover)
        d = config.allowances.get("MEAL")
        if d and d.get("rate") and (work_minutes > 300 or overtime_hours > 2):
            results.append({
                "type": "MEAL", "amount": _round2(d["rate"]),
                "reason": "Shift over 5 hours" if work_minutes > 300
                          else "Overtime over 2 hours",
            })

    if "KM_TRAVEL" in enabled and km_travelled and km_travelled > 0:
        d = config.allowances.get("KM_TRAVEL")
        if d and d.get("rate"):
            results.append({
                "type": "KM_TRAVEL",
                "amount": _round2(km_travelled * d["rate"]),
                "reason": f"{km_travelled} km travelled",
            })
    return results


# ---------------------------------------------------------------------------
# Sleep disturbances — sleepDisturbance.service
# ---------------------------------------------------------------------------


def process_sleep_disturbances(disturbances: list, base_rate: float,
                               config: EngineConfig, employment_type: str) -> dict:
    """Port of processSleepDisturbances — min 1h each, paid at the overtime rate."""
    if not disturbances:
        return {"count": 0, "total_charged_minutes": 0.0, "total_pay": 0.0}
    total_charged = 0.0
    for start, end in disturbances:
        raw = (end - start).total_seconds() / 60.0
        total_charged += max(raw, 60.0)                  # minimum 1 hour each
    ot_mult = get_shift_type_multiplier("OVERTIME", config, employment_type)
    total_pay = _round2((total_charged / 60.0) * base_rate * ot_mult)
    return {"count": len(disturbances),
            "total_charged_minutes": total_charged, "total_pay": total_pay}


# ---------------------------------------------------------------------------
# Orchestrator — processShift
# ---------------------------------------------------------------------------


def process_shift(start: datetime, end: datetime, config: EngineConfig, *,
                  employment_type: str, base_rate: float, is_sleepover: bool = False,
                  prev_shift_end: datetime | None = None,
                  prior_daily_hours: float = 0.0, prior_periodic_hours: float = 0.0,
                  periodic_threshold: float | None = None,
                  km_travelled: float = 0.0, disturbances: list | None = None,
                  enabled_allowances: set | None = None) -> dict:
    """Port of processShift — the unified payroll engine entry point."""
    if end <= start:
        raise CalculationError("Shift end must be after the start.")
    if base_rate <= 0:
        raise CalculationError("Base hourly rate must be greater than 0.")
    if periodic_threshold is None:
        periodic_threshold = config.weekly_ot_threshold
    if enabled_allowances is None:
        enabled_allowances = set(ALL_ALLOWANCE_TYPES)

    # 1. Segmentation.
    segments = build_shift_segments(
        start, end, config, force_sleepover=is_sleepover, allow_sleepover=is_sleepover
    )
    # 2. Type resolution + overtime tiering.
    resolved = resolve_all_segment_types(
        segments, config,
        prev_shift_end=prev_shift_end, first_shift_start_of_day=start,
        prior_daily_hours=prior_daily_hours, prior_periodic_hours=prior_periodic_hours,
        periodic_threshold=periodic_threshold, employment_type=employment_type,
    )
    # 3. Financial calculation.
    pay = calculate_shift_pay(resolved, base_rate, config, employment_type)

    # 4. Sleep disturbances (only when the sleepover flat rate applied).
    disturbance_result = {"count": 0, "total_charged_minutes": 0.0, "total_pay": 0.0}
    if pay["sleepover_flat_rate_applied"] and disturbances:
        disturbance_result = process_sleep_disturbances(
            disturbances, base_rate, config, employment_type
        )

    # 5. Allowances.
    overtime_hours = sum(
        p.seg.hours for p in pay["segment_payments"]
        if p.shift_type in ("OVERTIME", "OVERTIME_L2")
    )
    allowances = calculate_allowances(
        resolved, config, km_travelled=km_travelled,
        overtime_hours=overtime_hours, enabled=enabled_allowances,
    )
    # The sleepover flat rate is paid as segment pay; pay $60.02 once. If a
    # sleepover did not qualify for the flat rate, surface it as the allowance.
    if is_sleepover and not pay["sleepover_flat_rate_applied"] \
            and "SLEEPOVER" in enabled_allowances:
        rate = config.allowances.get("SLEEPOVER", {}).get("rate") or SLEEPOVER_FLAT_RATE
        allowances.append({"type": "SLEEPOVER", "amount": _round2(rate),
                           "reason": "Sleepover allowance"})

    return {
        "segment_payments": pay["segment_payments"],
        "base_pay": pay["base_pay"],
        "overtime_pay": pay["overtime_pay"],
        "work_pay": pay["total_pay"],
        "sleepover_flat_rate_applied": pay["sleepover_flat_rate_applied"],
        "allowances": allowances,
        "sleep_disturbances": disturbance_result,
    }


# ---------------------------------------------------------------------------
# Benchmark — `python services/payroll_engine.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Ticket Section 6 validation case: 18 Dec 21:30 -> 19 Dec 06:30,
    # casual base $35.67. Expected $444.54.
    cfg = EngineConfig()
    result = process_shift(
        datetime(2025, 12, 18, 21, 30), datetime(2025, 12, 19, 6, 30),
        cfg, employment_type="casual", base_rate=35.67,
    )
    for p in result["segment_payments"]:
        print(f"  {p.seg.start:%H:%M}-{p.seg.end:%H:%M}  {p.shift_type:12s} "
              f"x{p.rate}  ${p.pay}")
    gross = _round2(sum(p.pay for p in result["segment_payments"]))
    verdict = "PASS" if abs(gross - 444.54) < 0.01 else "FAIL"
    print(f"\nTicket benchmark — expected $444.54, got ${gross}  [{verdict}]")
