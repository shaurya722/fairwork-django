"""SCHADS Award Allowances (MA000100) - All Clause Values and Calculations.

This module implements the 7 comprehensive allowance modules as per the
SCHADS Award modernization requirements (post-June 2026 variations).

Allowance Categories:
1. Broken Shift Allowances (Clause 25.6)
2. Vehicle & Travel Allowances (Clause 20.7)
3. First Aid Allowance (Clause 20.6)
4. On-Call Allowance (Clause 20.11)
5. Meal Allowances (Clause 20.5)
6. Uniform & Laundry Allowance (Clause 20.2)
7. Enhanced Sleepover Validation (Post-June 2026)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# ALLOWANCE CONSTANTS (Current as of June 2026)
# ---------------------------------------------------------------------------

# Broken Shift Allowances (Clause 25.6)
BROKEN_SHIFT_2_PERIOD = 20.82  # Two separate work periods
BROKEN_SHIFT_3_PERIOD = 27.56  # Three separate work periods
BROKEN_SHIFT_MAX_SPAN_HOURS = 12  # Maximum span from first start to last end
BROKEN_SHIFT_MIN_ENGAGEMENT_DISABILITY = 2  # Hours per period (Disability/Home Care)
BROKEN_SHIFT_MIN_ENGAGEMENT_SOCIAL = 3  # Hours per period (Social & Community)

# Vehicle Allowance (Clause 20.7)
VEHICLE_RATE_PER_KM = 0.96  # Per kilometer when using own vehicle

# First Aid Allowance (Clause 20.6)
FIRST_AID_WEEKLY_FULL_TIME = 19.76  # Full-time weekly flat rate
FIRST_AID_HOURLY_PART_TIME = 0.52  # Part-time/casual per ordinary hour
FIRST_AID_WEEKLY_CAP = 19.76  # Maximum weekly accumulation for part-time

# On-Call Allowance (Clause 20.11)
ON_CALL_WEEKDAY_RATE = 24.50  # 7.5% of standard weekly rate (Mon-Fri)
ON_CALL_WEEKEND_RATE = 49.00  # 15% of standard weekly rate (Sat-Sun/PH)

# Meal Allowance (Clause 20.5)
MEAL_ALLOWANCE_OVERTIME = 16.62  # When working unexpected overtime (>1 hour)

# Uniform & Laundry (Clause 20.2)
UNIFORM_ALLOWANCE_WEEKLY = 1.49  # When uniform required but not provided
LAUNDRY_ALLOWANCE_PER_SHIFT = 0.32  # Per shift when laundering own uniform
LAUNDRY_ALLOWANCE_WEEKLY_CAP = 1.49  # Maximum weekly laundry allowance

# Sleepover (Post-June 2026 Revisions)
SLEEPOVER_ALLOWANCE = 60.02  # 4.9% of standard weekly rate per 8-hour block
SLEEPOVER_MIN_ACTIVE_HOURS = 4  # Minimum active hours required on one side


# ---------------------------------------------------------------------------
# MODULE 1: BROKEN SHIFT ALLOWANCES
# ---------------------------------------------------------------------------

class BrokenShiftValidation:
    """Validation result for broken shift compliance."""
    def __init__(self, valid: bool, allowance: float = 0.0, warnings: list[str] = None):
        self.valid = valid
        self.allowance = allowance
        self.warnings = warnings or []
        self.breach_type: str | None = None
        self.action_required: str | None = None


def calculate_broken_shift_allowance(
    periods: list[dict[str, Any]],
    stream: str | None = None
) -> BrokenShiftValidation:
    """Calculate broken shift allowance and validate compliance.
    
    Args:
        periods: List of work periods, each with 'start' and 'end' datetime
        stream: Employee stream (for minimum engagement validation)
    
    Returns:
        BrokenShiftValidation with allowance amount and any warnings
    """
    if not periods or len(periods) < 2:
        return BrokenShiftValidation(valid=False, warnings=["Not a broken shift"])
    
    if len(periods) > 3:
        return BrokenShiftValidation(
            valid=False,
            warnings=["Broken shifts can only have 2 or 3 periods"]
        )
    
    # Parse datetimes
    try:
        parsed_periods = []
        for p in periods:
            start = p['start'] if isinstance(p['start'], datetime) else datetime.fromisoformat(str(p['start']))
            end = p['end'] if isinstance(p['end'], datetime) else datetime.fromisoformat(str(p['end']))
            parsed_periods.append({'start': start, 'end': end})
    except (KeyError, ValueError) as e:
        return BrokenShiftValidation(valid=False, warnings=[f"Invalid period format: {e}"])
    
    # Sort by start time
    parsed_periods.sort(key=lambda p: p['start'])
    
    # Check 12-hour span rule
    first_start = parsed_periods[0]['start']
    last_end = parsed_periods[-1]['end']
    total_span = (last_end - first_start).total_seconds() / 3600
    
    if total_span > BROKEN_SHIFT_MAX_SPAN_HOURS:
        return BrokenShiftValidation(
            valid=False,
            warnings=[
                f"Broken shift span ({total_span:.1f}h) exceeds 12-hour maximum",
                "Final period must be paid as overtime (200%)"
            ],
            breach_type="12_HOUR_SPAN_EXCEEDED",
            action_required="FLAG_FINAL_PERIOD_AS_OVERTIME_200"
        )
    
    # Check minimum engagement per period
    min_engagement = BROKEN_SHIFT_MIN_ENGAGEMENT_SOCIAL
    if stream in ("HOME_CARE", "CRISIS_ACCOMMODATION", "FAMILY_DAY_CARE"):
        min_engagement = BROKEN_SHIFT_MIN_ENGAGEMENT_DISABILITY
    
    warnings = []
    for i, period in enumerate(parsed_periods, 1):
        duration = (period['end'] - period['start']).total_seconds() / 3600
        if duration < min_engagement:
            warnings.append(
                f"Period {i} ({duration:.1f}h) below minimum engagement ({min_engagement}h)"
            )
    
    if warnings:
        result = BrokenShiftValidation(valid=False, warnings=warnings)
        result.breach_type = "MINIMUM_ENGAGEMENT_BREACH"
        result.action_required = "UNDERPAYMENT_FLAG"
        return result
    
    # Calculate allowance
    num_periods = len(parsed_periods)
    if num_periods == 2:
        allowance = BROKEN_SHIFT_2_PERIOD
    elif num_periods == 3:
        allowance = BROKEN_SHIFT_3_PERIOD
    else:
        allowance = 0.0
    
    return BrokenShiftValidation(
        valid=True,
        allowance=allowance,
        warnings=[f"Broken shift allowance: {num_periods} periods"]
    )


# ---------------------------------------------------------------------------
# MODULE 2: VEHICLE & TRAVEL ALLOWANCES
# ---------------------------------------------------------------------------

def calculate_vehicle_allowance(km_driven: float) -> dict[str, Any]:
    """Calculate vehicle allowance for using own vehicle.
    
    Args:
        km_driven: Total kilometers driven for work purposes
    
    Returns:
        Dict with allowance amount and details
    """
    if km_driven <= 0:
        return {"allowance": 0.0, "km": 0, "rate": VEHICLE_RATE_PER_KM}
    
    allowance = km_driven * VEHICLE_RATE_PER_KM
    return {
        "allowance": round(allowance, 2),
        "km": km_driven,
        "rate": VEHICLE_RATE_PER_KM,
        "description": f"{km_driven}km × ${VEHICLE_RATE_PER_KM}/km"
    }


def calculate_travel_time_pay(
    travel_minutes: float,
    hourly_rate: float,
    is_weekend: bool = False,
    penalty_multiplier: float = 1.0
) -> dict[str, Any]:
    """Calculate pay for travel time between client sites.
    
    Travel time between clients is paid at ordinary rate (or penalty rate
    if on weekends) and counts toward daily ordinary hours pool.
    
    Args:
        travel_minutes: Minutes spent traveling between clients
        hourly_rate: Base hourly rate
        is_weekend: Whether travel occurred on weekend
        penalty_multiplier: Penalty rate multiplier if applicable
    
    Returns:
        Dict with pay amount and details
    """
    if travel_minutes <= 0:
        return {"pay": 0.0, "hours": 0.0, "counts_as_ordinary": True}
    
    travel_hours = travel_minutes / 60
    effective_rate = hourly_rate * penalty_multiplier
    pay = travel_hours * effective_rate
    
    return {
        "pay": round(pay, 2),
        "hours": round(travel_hours, 2),
        "rate": effective_rate,
        "counts_as_ordinary": True,
        "description": f"Travel time: {travel_minutes}min × ${effective_rate:.2f}/h"
    }


# ---------------------------------------------------------------------------
# MODULE 3: FIRST AID ALLOWANCE
# ---------------------------------------------------------------------------

def calculate_first_aid_allowance(
    employment_type: str,
    ordinary_hours_worked: float,
    weeks_in_period: float = 1.0
) -> dict[str, Any]:
    """Calculate first aid allowance.
    
    Args:
        employment_type: "FULL_TIME", "PART_TIME", or "CASUAL"
        ordinary_hours_worked: Ordinary hours worked in the period
        weeks_in_period: Number of weeks in the calculation period
    
    Returns:
        Dict with allowance amount and details
    """
    if employment_type == "FULL_TIME":
        allowance = FIRST_AID_WEEKLY_FULL_TIME * weeks_in_period
        return {
            "allowance": round(allowance, 2),
            "type": "weekly_flat_rate",
            "weeks": weeks_in_period,
            "description": f"First aid (full-time): ${FIRST_AID_WEEKLY_FULL_TIME}/week × {weeks_in_period} weeks"
        }
    
    # Part-time / Casual: pro-rata per ordinary hour
    allowance = ordinary_hours_worked * FIRST_AID_HOURLY_PART_TIME
    
    # Cap at weekly maximum
    weekly_cap = FIRST_AID_WEEKLY_CAP * weeks_in_period
    if allowance > weekly_cap:
        allowance = weekly_cap
        capped = True
    else:
        capped = False
    
    return {
        "allowance": round(allowance, 2),
        "type": "hourly_pro_rata",
        "hours": ordinary_hours_worked,
        "rate": FIRST_AID_HOURLY_PART_TIME,
        "capped": capped,
        "cap": weekly_cap,
        "description": f"First aid: {ordinary_hours_worked}h × ${FIRST_AID_HOURLY_PART_TIME}/h" + 
                      (f" (capped at ${weekly_cap})" if capped else "")
    }


# ---------------------------------------------------------------------------
# MODULE 4: ON-CALL ALLOWANCE
# ---------------------------------------------------------------------------

def calculate_on_call_allowance(day_type: str) -> dict[str, Any]:
    """Calculate on-call allowance.
    
    Args:
        day_type: "weekday", "weekend", or "public_holiday"
    
    Returns:
        Dict with allowance amount and details
    """
    if day_type in ("weekend", "public_holiday"):
        allowance = ON_CALL_WEEKEND_RATE
        description = "On-call (weekend/public holiday)"
    else:
        allowance = ON_CALL_WEEKDAY_RATE
        description = "On-call (weekday)"
    
    return {
        "allowance": round(allowance, 2),
        "day_type": day_type,
        "description": description
    }


# ---------------------------------------------------------------------------
# MODULE 5: MEAL ALLOWANCES
# ---------------------------------------------------------------------------

def calculate_meal_allowance(
    unexpected_overtime_hours: float,
    notice_given: bool
) -> dict[str, Any]:
    """Calculate meal allowance for unexpected overtime.
    
    Triggered when employee works >1 hour of unexpected overtime without
    notice given on or before the previous day.
    
    Args:
        unexpected_overtime_hours: Hours of unexpected overtime worked
        notice_given: Whether notice was given on/before previous day
    
    Returns:
        Dict with allowance amount and details
    """
    if notice_given or unexpected_overtime_hours <= 1.0:
        return {
            "allowance": 0.0,
            "triggered": False,
            "reason": "Notice given" if notice_given else "Overtime ≤1 hour"
        }
    
    return {
        "allowance": MEAL_ALLOWANCE_OVERTIME,
        "triggered": True,
        "overtime_hours": unexpected_overtime_hours,
        "description": f"Meal allowance (unexpected OT: {unexpected_overtime_hours}h)"
    }


# ---------------------------------------------------------------------------
# MODULE 6: UNIFORM & LAUNDRY ALLOWANCE
# ---------------------------------------------------------------------------

def calculate_uniform_laundry_allowance(
    uniform_required: bool,
    uniform_provided: bool,
    laundry_required: bool,
    shifts_worked: int,
    weeks_in_period: float = 1.0
) -> dict[str, Any]:
    """Calculate uniform and laundry allowances.
    
    Args:
        uniform_required: Whether uniform is mandatory
        uniform_provided: Whether employer provides uniform for free
        laundry_required: Whether employee launders uniform themselves
        shifts_worked: Number of shifts worked in period
        weeks_in_period: Number of weeks in calculation period
    
    Returns:
        Dict with allowance amounts and details
    """
    result = {
        "uniform_allowance": 0.0,
        "laundry_allowance": 0.0,
        "total": 0.0,
        "details": []
    }
    
    # Uniform allowance (if required but not provided)
    if uniform_required and not uniform_provided:
        result["uniform_allowance"] = UNIFORM_ALLOWANCE_WEEKLY * weeks_in_period
        result["details"].append(
            f"Uniform allowance: ${UNIFORM_ALLOWANCE_WEEKLY}/week × {weeks_in_period} weeks"
        )
    
    # Laundry allowance (if laundering own uniform)
    if laundry_required and shifts_worked > 0:
        laundry = shifts_worked * LAUNDRY_ALLOWANCE_PER_SHIFT
        
        # Cap at weekly maximum
        weekly_cap = LAUNDRY_ALLOWANCE_WEEKLY_CAP * weeks_in_period
        if laundry > weekly_cap:
            laundry = weekly_cap
            capped = True
        else:
            capped = False
        
        result["laundry_allowance"] = round(laundry, 2)
        result["details"].append(
            f"Laundry allowance: {shifts_worked} shifts × ${LAUNDRY_ALLOWANCE_PER_SHIFT}" +
            (f" (capped at ${weekly_cap})" if capped else "")
        )
    
    result["total"] = round(result["uniform_allowance"] + result["laundry_allowance"], 2)
    return result


# ---------------------------------------------------------------------------
# MODULE 7: ENHANCED SLEEPOVER VALIDATION
# ---------------------------------------------------------------------------

class SleepooverValidation:
    """Validation result for sleepover compliance (post-June 2026)."""
    def __init__(self, valid: bool, allowance: float = 0.0, warnings: list[str] = None):
        self.valid = valid
        self.allowance = allowance
        self.warnings = warnings or []
        self.active_hours_before: float = 0.0
        self.active_hours_after: float = 0.0
        self.meets_4hour_rule: bool = False


def validate_sleepover_4hour_rule(
    active_hours_before: float,
    active_hours_after: float,
    sleepover_hours: float = 8.0
) -> SleepooverValidation:
    """Validate sleepover against 4-hour active threshold rule.
    
    The sleepover allowance requires a minimum of 4 continuous active hours
    on AT LEAST ONE side of the sleepover (before OR after, not split).
    
    Args:
        active_hours_before: Active work hours before sleepover
        active_hours_after: Active work hours after sleepover
        sleepover_hours: Duration of sleepover period (default 8)
    
    Returns:
        SleepooverValidation with compliance status and warnings
    """
    result = SleepooverValidation(valid=False, allowance=SLEEPOVER_ALLOWANCE)
    result.active_hours_before = active_hours_before
    result.active_hours_after = active_hours_after
    
    # Check if either side meets the 4-hour threshold
    if active_hours_before >= SLEEPOVER_MIN_ACTIVE_HOURS:
        result.valid = True
        result.meets_4hour_rule = True
        result.warnings.append(
            f"✅ 4-hour rule met: {active_hours_before}h active before sleepover"
        )
    elif active_hours_after >= SLEEPOVER_MIN_ACTIVE_HOURS:
        result.valid = True
        result.meets_4hour_rule = True
        result.warnings.append(
            f"✅ 4-hour rule met: {active_hours_after}h active after sleepover"
        )
    else:
        result.valid = False
        result.meets_4hour_rule = False
        result.allowance = 0.0
        result.warnings.append(
            f"❌ COMPLIANCE BREACH: No 4-hour active block found "
            f"(before: {active_hours_before}h, after: {active_hours_after}h)"
        )
        result.warnings.append(
            "Sleepover allowance INVALID - requires minimum 4 continuous active hours "
            "on at least ONE side of the sleepover"
        )
    
    return result


# ---------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def format_allowance_ledger(allowances: dict[str, Any]) -> str:
    """Format allowances as a clean Markdown table.
    
    Args:
        allowances: Dict of allowance calculations
    
    Returns:
        Formatted Markdown table string
    """
    lines = [
        "### Allowance Ledger",
        "",
        "| Allowance | Units | Rate/Multiplier | Amount |",
        "|-----------|-------|-----------------|--------|"
    ]
    
    total = 0.0
    
    for name, data in allowances.items():
        if isinstance(data, dict) and data.get("allowance", 0) > 0:
            amount = data["allowance"]
            total += amount
            
            units = data.get("units", data.get("hours", data.get("km", "-")))
            rate = data.get("rate", data.get("multiplier", "-"))
            
            lines.append(f"| {name} | {units} | {rate} | ${amount:.2f} |")
    
    lines.append(f"| **TOTAL ALLOWANCES** | | | **${total:.2f}** |")
    lines.append("")
    
    return "\n".join(lines)
