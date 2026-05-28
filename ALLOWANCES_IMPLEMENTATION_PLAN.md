# SCHADS Allowances Implementation Plan

## Overview
Integrate 7 comprehensive allowance modules into the chatbot's SCHADS calculation engine to provide full compliance with the SCHADS Award (MA000100).

---

## Current State Analysis

### Existing Components
1. **`services/payroll_engine.py`** - Core calculation engine (Node.js port)
2. **`services/schads.py`** - Adapter between chatbot and engine
3. **`services/llm.py`** - Extraction prompt for user questions
4. **`services/rag.py`** - RAG pipeline with calculation routing

### What's Already Supported
- ✅ Basic hourly rates (casual/permanent)
- ✅ Penalty rates (evening, night, weekend, public holiday)
- ✅ Overtime (level 1 & 2)
- ✅ Sleepover allowance (flat rate)
- ✅ Meal breaks
- ✅ Public holidays

### What Needs to Be Added
- ❌ Broken shift allowances (2-period & 3-period)
- ❌ Vehicle & travel allowances
- ❌ First aid allowance
- ❌ On-call allowance
- ❌ Meal allowance (overtime overrun)
- ❌ Uniform & laundry allowance
- ❌ Enhanced sleepover validation (4-hour active threshold)

---

## Implementation Strategy

### Phase 1: Extend LLM Extraction Schema
**File**: `services/llm.py`

Add new fields to `EXTRACTION_SYSTEM_PROMPT`:
```json
{
  "shifts": [{
    "is_broken_shift": boolean,
    "broken_shift_periods": number,  // 2 or 3
    "kms_driven": number,
    "travel_time_minutes": number
  }],
  "employee": {
    "has_first_aid_certificate": boolean,
    "is_on_call": boolean,
    "on_call_day_type": "weekday" | "weekend" | null
  },
  "tenant_config": {
    "meal_allowance": boolean,
    "uniform_allowance": boolean,
    "laundry_allowance": boolean,
    "first_aid_allowance": boolean,
    "on_call_allowance": boolean,
    "vehicle_allowance": boolean
  }
}
```

### Phase 2: Extend Payroll Engine
**File**: `services/payroll_engine.py`

Add allowance calculation functions:
1. `calculate_broken_shift_allowance(periods: int) -> float`
2. `calculate_vehicle_allowance(kms: float) -> float`
3. `calculate_first_aid_allowance(employment_type: str, hours: float) -> float`
4. `calculate_on_call_allowance(day_type: str) -> float`
5. `calculate_meal_allowance(overtime_hours: float, notice_given: bool) -> float`
6. `calculate_uniform_laundry_allowance(shifts: int) -> float`
7. `validate_sleepover_4hour_rule(shift_data) -> dict`

### Phase 3: Update SCHADS Adapter
**File**: `services/schads.py`

Modify `calculate_pay()` to:
1. Process allowances after shift calculations
2. Add allowance line items to result
3. Include compliance warnings
4. Generate allowance validation alerts

### Phase 4: Enhance RAG Pipeline
**File**: `services/rag.py`

Update `_inject_calc_defaults()` to:
1. Detect allowance keywords in user questions
2. Set appropriate tenant_config flags
3. Extract allowance-specific parameters

### Phase 5: Update Response Formatting
**File**: `services/llm.py`

Add new system prompt for allowance explanations:
```python
ALLOWANCE_EXPLANATION_PROMPT = """
You explain SCHADS allowances in plain English...
"""
```

---

## Allowance Constants (Clause Values)

```python
# Broken Shift Allowances (Clause 25.6)
BROKEN_SHIFT_2_PERIOD = 20.82
BROKEN_SHIFT_3_PERIOD = 27.56
BROKEN_SHIFT_MAX_SPAN_HOURS = 12

# Vehicle Allowance (Clause 20.7)
VEHICLE_RATE_PER_KM = 0.96

# First Aid Allowance (Clause 20.6)
FIRST_AID_WEEKLY_FULL_TIME = 19.76
FIRST_AID_HOURLY_PART_TIME = 0.52
FIRST_AID_WEEKLY_CAP = 19.76

# On-Call Allowance (Clause 20.11)
ON_CALL_WEEKDAY_RATE = 24.50  # 7.5% of standard weekly
ON_CALL_WEEKEND_RATE = 49.00  # 15% of standard weekly

# Meal Allowance (Clause 20.5)
MEAL_ALLOWANCE_OVERTIME = 16.62

# Uniform & Laundry (Clause 20.2)
UNIFORM_ALLOWANCE_WEEKLY = 1.49
LAUNDRY_ALLOWANCE_PER_SHIFT = 0.32
LAUNDRY_ALLOWANCE_WEEKLY_CAP = 1.49

# Sleepover (Post-June 2026)
SLEEPOVER_ALLOWANCE = 60.02  # 4.9% of standard weekly
SLEEPOVER_MIN_ACTIVE_HOURS = 4
```

---

## Detection Keywords for LLM

### Broken Shift
- "broken shift", "split shift", "two periods", "three periods"
- "unpaid break between", "gap between shifts"

### Vehicle/Travel
- "drive", "drove", "km", "kilometers", "travel between"
- "use my car", "own vehicle", "mileage"

### First Aid
- "first aid", "first aid certificate", "qualified first aider"

### On-Call
- "on call", "on-call", "standby", "available after hours"

### Meal Allowance
- "unexpected overtime", "stayed late", "no notice"
- "meal with client", "dining with participant"

### Uniform/Laundry
- "uniform", "laundry", "wash my clothes", "soiled clothing"

---

## Compliance Validation Rules

### Broken Shift Validation
```python
def validate_broken_shift(shift):
    total_span = end_time - start_time
    if total_span > timedelta(hours=12):
        return {
            "valid": False,
            "breach": "12-hour span exceeded",
            "action": "Flag final period as overtime (200%)"
        }
    
    for period in periods:
        if period.duration < minimum_engagement:
            return {
                "valid": False,
                "breach": "Period below minimum engagement",
                "action": "Underpayment breach"
            }
    
    return {"valid": True}
```

### Sleepover 4-Hour Rule
```python
def validate_sleepover_4hour_rule(shift):
    active_before = calculate_active_hours_before_sleepover()
    active_after = calculate_active_hours_after_sleepover()
    
    if active_before >= 4 or active_after >= 4:
        return {"valid": True}
    
    return {
        "valid": False,
        "breach": "No 4-hour active block on either side",
        "action": "Sleepover allowance invalid"
    }
```

---

## Output Format Enhancement

### Current Output
```
Work $450.00 + allowances $0.00 = gross $450.00
```

### Enhanced Output
```
=== SCHADS PAY CALCULATION ===

WORK HOURS:
• Day / ordinary hours: 6h × 1.0 = $180.00 (Clause 25)
• Saturday: 2h × 1.5 = $90.00 (Clause 26)

ALLOWANCES:
• Broken shift (2 periods): $20.82 (Clause 25.6)
• Vehicle allowance: 45km × $0.96 = $43.20 (Clause 20.7)
• First aid allowance: 8h × $0.52 = $4.16 (Clause 20.6)

TOTALS:
Work: $270.00
Allowances: $68.18
Gross Pay: $338.18

COMPLIANCE ALERTS:
✅ All periods meet minimum engagement
✅ Broken shift span within 12-hour limit
⚠️  First aid allowance capped at weekly maximum
```

---

## Testing Strategy

### Test Cases Required

1. **Broken Shift - 2 Periods**
   - Input: "Calculate pay for 4 hours 8am-12pm, then 4 hours 2pm-6pm"
   - Expected: Base pay + $20.82 allowance

2. **Broken Shift - 3 Periods**
   - Input: "3 hours 7am-10am, 3 hours 12pm-3pm, 3 hours 5pm-8pm"
   - Expected: Base pay + $27.56 allowance

3. **Broken Shift - 12 Hour Breach**
   - Input: "4 hours 6am-10am, then 4 hours 8pm-12am"
   - Expected: Warning about 14-hour span, overtime on final period

4. **Vehicle Allowance**
   - Input: "8 hour shift, drove 45km between clients"
   - Expected: Base pay + (45 × $0.96) = +$43.20

5. **First Aid - Part Time**
   - Input: "8 hours with first aid certificate"
   - Expected: Base pay + (8 × $0.52) = +$4.16

6. **On-Call - Weekend**
   - Input: "On call Saturday night"
   - Expected: $49.00 allowance

7. **Sleepover - 4 Hour Rule Pass**
   - Input: "5 hours 4pm-9pm, sleepover 10pm-6am, 3 hours 7am-10am"
   - Expected: Base pay + sleepover allowance

8. **Sleepover - 4 Hour Rule Fail**
   - Input: "2 hours 8pm-10pm, sleepover 10pm-6am, 2 hours 7am-9am"
   - Expected: Compliance breach warning

---

## Migration Path

### Step 1: Non-Breaking Addition
- Add new allowance fields as **optional**
- Default all new flags to `false`
- Existing calculations continue to work

### Step 2: Gradual Rollout
- Phase 1: Broken shift + vehicle (most requested)
- Phase 2: First aid + on-call
- Phase 3: Enhanced sleepover validation

### Step 3: Documentation
- Update API docs
- Add example prompts to `chatbot_test_prompts.md`
- Create allowance guide for users

---

## Files to Modify

1. ✏️ `services/llm.py` - Extraction schema + detection rules
2. ✏️ `services/payroll_engine.py` - Allowance calculation functions
3. ✏️ `services/schads.py` - Adapter integration
4. ✏️ `services/rag.py` - Keyword detection
5. ✏️ `chatbot_test_prompts.md` - Test cases
6. 📄 `ALLOWANCES_GUIDE.md` - User documentation (new)

---

## Estimated Effort

- **LLM Schema Updates**: 2 hours
- **Payroll Engine Functions**: 4 hours
- **SCHADS Adapter Integration**: 3 hours
- **RAG Pipeline Updates**: 2 hours
- **Testing & Validation**: 4 hours
- **Documentation**: 2 hours

**Total**: ~17 hours

---

## Next Steps

1. ✅ Review this plan with stakeholders
2. ⏳ Implement Phase 1 (LLM extraction)
3. ⏳ Implement Phase 2 (payroll engine)
4. ⏳ Implement Phase 3 (SCHADS adapter)
5. ⏳ Test with real-world scenarios
6. ⏳ Deploy to production
