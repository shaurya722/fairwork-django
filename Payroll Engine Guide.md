# Payroll / Pay Rate Calculation Logic — Complete Engine Guide

> Service: `pricing-service`
> Entry Point: `POST /payroll/calculate` (`calculatePayroll` controller)
> Auth: Bearer token + `x-user-tenant-id` header
> Award: SCHADS (Social, Community, Home Care and Disability Services)

---

## Table of Contents

1. High-Level Flow
2. Input Parameters
3. Configuration Loading
4. Shift Segmentation
5. Shift Type Resolution
6. Pay Calculation
7. Overtime Calculation
8. Allowances
9. Broken Shift Allowance
10. Sleep Disturbances
11. Tax Calculation (PAYG)
12. Summary Response Structure

---

## 1. High-Level Flow

The payroll engine runs in 7 sequential stages:

```
1. Load Config    -> Tenant rules, shift definitions, allowances, holidays
2. Segment Shift  -> Split by shift definitions, midnight, sleepover windows
3. Resolve Types  -> Public holiday, weekend, sleepover, overtime triggers
4. Calculate Pay  -> Apply multipliers, sleepover flat rate, paid gap time
5. Allowances     -> Laundry, uniform, meal, km travel, sleepover, broken shift
6. Overtime       -> Weekly / fortnightly / monthly threshold checks
7. Tax (PAYG)     -> ATO bracket formula, per-item breakdown
```

---

## 2. Input Parameters

```json
{
  "shiftId": "string (external shift identifier)",
  "staffId": "string (UUID)",
  "staffName": "string",
  "employmentType": "CASUAL | FULL_TIME | PART_TIME",
  "baseRate": "number (hourly base rate in AUD)",
  "start": "ISO datetime (shift start)",
  "end": "ISO datetime (shift end)",
  "sleepDisturbances": [
    { "timestamp": "ISO datetime", "durationMinutes": 30, "reason": "string" }
  ],
  "isSleepover": "boolean",
  "kmTravelled": "number (optional)",
  "isRemote": "boolean (remote area loading)",
  "year": "number (financial year, e.g. 2025)",
  "enabledAllowances": ["MEAL", "LAUNDRY", "UNIFORM", "KM_TRAVEL", "SLEEPOVER"],
  "timezone": "string (e.g. 'Australia/Sydney')"
}
```

---

## 3. Configuration Loading

### 3.1 Tenant Config (`buildTenantConfig`)
Loaded from DB for the given `tenantId` and `year`:

| Component | Source Table | Description |
|-----------|-------------|-------------|
| `shiftDefinitions` | `pricing.shift_definitions` | Time windows (DAY, AFTERNOON, NIGHT, SLEEPOVER) with rates per employment type |
| `rules` | `rule` | MAX_WEEKLY_HOURS, MAX_FORTNIGHT_HOURS, MAX_MONTHLY_HOURS, PAYMENT_FREQUENCY, OVERTIME_AFTER_HOURS, START_OF_WEEK, MINIMUM_ENGAGEMENT_MINUTES |
| `allowances` | `allowance` | Per-shift rates for LAUNDRY, UNIFORM, MEAL, KM_TRAVEL, SLEEPOVER, BROKENSHIFT_1, BROKENSHIFT_2 |
| `holidays` | `holiday` | Public holidays for the tenant (or `tenantId: 'default'`) |

### 3.2 Shift Definition Schema
Each definition has time window + 6 rate columns:
```ts
{
  type: 'DAY' | 'AFTERNOON' | 'NIGHT' | 'SLEEPOVER' | 'SATURDAY' | 'SUNDAY' | 'PUBLIC_HOLIDAY',
  startTime: '06:00',      // HH:mm in local timezone
  endTime: '20:00',
  casualRate: 1.25,        // multiplier over baseRate
  fullTimeRate: 1.0,
  partTimeRate: 1.0,
  remoteCasualRate: null,  // override if remote area
  remoteFullTimeRate: null,
  remotePartTimeRate: null
}
```

### 3.3 Default Rules (fallbacks)
- `MAX_WEEKLY_HOURS` = 38
- `MAX_FORTNIGHT_HOURS` = 76
- `MAX_MONTHLY_HOURS` = 152
- `PAYMENT_FREQUENCY` = 2 (WEEKLY)
- `OVERTIME_AFTER_HOURS` = 10 (daily threshold in 24h window)

---

## 4. Shift Segmentation

### 4.1 Time-Based Splitting (`splitByShiftDefinition`)
The shift is sliced at every boundary where the **local timezone** time crosses:
1. **Shift definition boundaries** — e.g. 06:00, 20:00, 22:00
2. **Midnight** — compulsorily split at each calendar day change (unless inside a sleepover window)
3. **Sleepover boundaries** — if `isSleepover=true`, boundaries at sleepover start/end times

The resulting segments are tagged with the matching `ShiftDefinition` type.

### 4.2 Sleepover Handling
When `isSleepover=true`:
- If no sleepover definition exists in DB, a fallback `22:00–06:00` window is injected.
- Midnight splits are **skipped** if the shift overlaps with a sleepover window.
- The shift is split into: **prefix work** -> **sleepover** -> **suffix work**.

### 4.3 Minimum Engagement Rule
If total work duration (excluding sleepover) is less than the tenant's `MINIMUM_ENGAGEMENT_MINUTES` rule:
- A **PAID_GAP_TIME** segment is appended after the last work block.
- The gap duration = `minimumEngagementMinutes - totalWorkDuration`.
- **Exception:** If a work block immediately follows a sleepover block, no gap time is added (treated as a continuation).

---

## 5. Shift Type Resolution

Each segment is resolved to a final `shiftType` using this **priority order**:

### 5.1 Priority Stack
1. **Public Holiday** — highest rate wins, no ordinary loadings
2. **Weekend** — Saturday or Sunday
3. **Sleepover** — if segment is inside sleepover window
4. **Forced Type** — from overtime/break violation rules
5. **Natural Type** — from shift definition matching (DAY, AFTERNOON, NIGHT)

### 5.2 Overtime Triggers
A segment (or sub-piece of a segment) is upgraded to `OVERTIME` or `OVERTIME_L2` when any of these fire:

| Trigger | Condition | Threshold Source |
|---------|-----------|-----------------|
| **Daily Overtime** | Cumulative work in 24h window > threshold | `OVERTIME_AFTER_HOURS` rule (default: 10h) |
| **Periodic Overtime** | Prior period hours + current shift > threshold | `MAX_WEEKLY_HOURS` (38), `MAX_FORTNIGHT_HOURS` (76), `MAX_MONTHLY_HOURS` (152) |
| **Span Violation** | Gap between previous shift end and current shift start < min break threshold | Rule or default 10h |
| **Daily Overtime L2** | Cumulative work in 24h > `OVERTIME_AFTER_HOURS + 2` | e.g. 12h |
| **Periodic Overtime L2** | Period hours > threshold + 2 | e.g. weekly 40h |

**L2 Tiering:**
- First 2 hours of overtime = `OVERTIME` (L1)
- Remaining overtime hours = `OVERTIME_L2` (L2)

### 5.3 Evening Trigger Rule
If any segment ends **after 20:00 (8 PM)** local time, all earlier segments on the same day that would otherwise be `DAY` are upgraded to `AFTERNOON` (if AFTERNOON rate > DAY rate).

### 5.4 Rate Comparison (Weekend vs Overtime)
When both weekend and overtime apply, the **higher multiplier wins**:
```
if (overtimeMultiplier >= weekendMultiplier) -> use OVERTIME
else -> use WEEKEND (SATURDAY / SUNDAY)
```

### 5.5 Multiplier Resolution (`getShiftTypeMultiplier`)
```ts
// 1. Look up definition in DB for the resolved shiftType
// 2. Pick rate column based on employmentType + isRemote
//    CASUAL  -> remote ? remoteCasualRate  : casualRate
//    FULL_TIME -> remote ? remoteFullTimeRate : fullTimeRate
//    PART_TIME -> remote ? remotePartTimeRate : partTimeRate
// 3. Fallback to SCHADS standard multipliers if DB missing:
//    DAY=1.0, AFTERNOON=1.125, NIGHT=1.15, SAT=1.5, SUN=2.0,
//    PH=2.5, OVERTIME=1.5, OVERTIME_L2=2.0, PAID_GAP=1.0
```

---

## 6. Pay Calculation

### 6.1 Segment Pay Formula
```
pay = round( hours x baseRate x multiplier )
```

### 6.2 Sleepover Flat Rate
When sleepover is enabled AND qualifies:
- **Qualification:** prefix work >= 4 hours OR suffix work >= 4 hours AND shift ends at or after the sleepover definition end time.
- **Payment:** The **first** sleepover segment receives a **flat rate** (default `$60.02` or from `allowance.rate` where `type='SLEEPOVER'`). All remaining sleepover segments pay `$0`.
- If **not qualified:** sleepover segments are paid at normal sleepover multiplier (falls back to NIGHT rate).

### 6.3 Effective Base Rate
```ts
effectiveBaseRate = rawBaseRate x dayShiftMultiplier
```
Where `dayShiftMultiplier` comes from the DB `DAY` definition for the employment type (casual loading multiplier, e.g. 1.25 for casual).

---

## 7. Overtime Calculation

### 7.1 Prior Hours Calculation
Before processing the current shift, the engine fetches:
- `priorDailyHours` — sum of WORK segment hours from prior shifts on the same local calendar day.
- `priorPeriodicHours` — aggregated weekly/fortnightly/monthly hours from `payrollHours` table.

### 7.2 Threshold Gaps
The engine computes the **smallest remaining gap** before any overtime threshold is hit:
```ts
gaps = [
  { reason: 'Weekly',  gap: 38 - currentWeeklyHours },
  { reason: 'Fortnightly', gap: 76 - currentFortnightlyHours },  // if freq >= 3
  { reason: 'Monthly', gap: 152 - currentMonthlyHours },       // if freq >= 4
];
minGap = gaps with smallest gap value;
```
The `periodicOvertimeThreshold` = `primaryPrior + minGap`.

### 7.3 Weekly / Fortnightly / Monthly Overtime Data
```ts
// Same formula for all three periods:
if (totalHours > threshold) {
  totalOT = totalHours - threshold;
  l1Hours = min(totalOT, 2);        // first 2 hours = L1
  l2Hours = max(0, totalOT - 2);    // remainder = L2
  normalHours = threshold;
}

// Multipliers
l1Multiplier = isCasual ? 1.75 : 1.5;
l2Multiplier = isCasual ? 2.25 : 2.0;
```

### 7.4 Overtime Pay
```ts
weeklyNormalPay   = normalHours   x rawBaseRate x dayShiftMultiplier;
weeklyOvertimeL1Pay = l1Hours x rawBaseRate x l1Multiplier;
weeklyOvertimeL2Pay = l2Hours x rawBaseRate x l2Multiplier;
```
Same formula applies to fortnightly and monthly.

### 7.5 Payment Frequency Mapping
```ts
1 -> DAILY
2 -> WEEKLY     (default)
3 -> FORTNIGHTLY
4 -> MONTHLY
```

---

## 8. Allowances

### 8.1 Laundry Allowance
```
weeklyRemaining = maxPerWeek - weeklyAllowanceTotals.LAUNDRY
amount = min(rate, weeklyRemaining)
```
Capped per week; tracked in `payrollHours.laundryPaid`.

### 8.2 Uniform Allowance
Same logic as laundry, tracked in `payrollHours.uniformPaid`.

### 8.3 Meal Allowance
```
eligible if (totalShiftMinutes > 300) OR (overtimeHours > 2)
amount = rate (fixed per shift)
```

### 8.4 KM Travel Allowance
```
amount = kmTravelled x rate (per km)
```

### 8.5 Sleepover Allowance
```
eligible if shift contains a sleepover segment
amount = rate (from allowance table, separate from flat rate)
```

### 8.6 Broken Shift Allowance
See Broken Shift Allowance section below.

---

## 9. Broken Shift Allowance

### 9.1 Sequence Rule
For a staff member on a given date, shifts are ordered by start time:
```
Shift 1  -> normal
Shift 2  -> broken (1st broken shift)
Shift 3  -> broken (2nd broken shift)
Shift 4+ -> normal
```
Only shifts 2 and 3 in a day can be "broken".

### 9.2 Allowance Lookup
```ts
// For the current shift, find its position in the day's sequence:
if (position === 2) allowanceType = 'BROKENSHIFT_1';
if (position === 3) allowanceType = 'BROKENSHIFT_2';

// Fetch rate from allowance table:
rate = await prisma.allowance.findFirst({
  where: { tenantId, year, type: allowanceType }
});
```

### 9.3 Application
The broken shift allowance amount is added to the total allowances and included in the tax calculation.

---

## 10. Sleep Disturbances

### 10.1 When Applied
Only when **sleepover flat rate is applied** AND `sleepDisturbances` array is non-empty.

### 10.2 Calculation
Each disturbance is a time interval (start -> end). The pay is calculated based on:
- The disturbance duration
- Base rate and applicable multiplier from shift definitions
- Minimum disturbance hours rule (if configured)

The total disturbance pay is added to the shift summary.

---

## 11. Tax Calculation (PAYG)

### 11.1 Frequency
Tax is calculated using the **payment frequency** (WEEKLY, FORTNIGHTLY, MONTHLY).

### 11.2 Taxable Income Components
| Component | Tax Treatment |
|-----------|--------------|
| Salary (normal pay) | Fully taxable via ATO bracket |
| Overtime pay | Fully taxable via ATO bracket |
| Laundry / Uniform allowance | Tax-free up to annual limit ($150/year) |
| KM Travel allowance | Tax-free up to `0.85 x km` (max 5,000 km/year) |
| Meal allowance (overtime) | Tax-free up to $35.65 per occasion |
| Broken shift allowance | Taxable |
| Task / skill allowance | Taxable |

### 11.3 ATO Bracket Formula
```ts
// For each frequency, ATO brackets define:
// lessThan: upper bound of bracket
// a: base tax amount
// b: cents per dollar over the lower bound

taxWithheld = a + floor((taxableGross + 0.99) x b) / 100;
```
Brackets are fetched from `tax_bracket` table per tenant/year/frequency.

### 11.4 Calculation Steps
1. Build `TaxLineItem[]` for wages + allowances + redundancy + government payments.
2. Separate **concessional-rate** items (e.g. unused annual leave on redundancy = 32% flat).
3. Sum all **bracket-formula taxable amounts**.
4. Call `calculateTax({ taxableGross, frequency, brackets })`.
5. **Apportion** the bracket tax across contributing line items proportionally.
6. `netPay = totalGross - totalTaxWithheld`.

### 11.5 Response Breakdown
```json
{
  "tax": {
    "frequency": "WEEKLY",
    "taxBracketUsed": "< $1,202 (a=0, b=0.165)",
    "itemBreakdown": [
      { "category": "WAGES", "item": "Salary & Wages", "gross": "$920.00", "taxFree": "$0.00", "taxable": "$920.00", "taxWithheld": "$151.80" },
      { "category": "ALLOWANCES", "item": "KM Travel Allowance", "gross": "$25.00", "taxFree": "$21.25", "taxable": "$3.75", "taxWithheld": "$0.62" }
    ],
    "totals": {
      "grossPay": "$945.00",
      "totalTaxFree": "$21.25",
      "totalTaxable": "$923.75",
      "totalTaxWithheld": "$152.42",
      "netPay": "$792.58"
    }
  }
}
```

---

## 12. Summary Response Structure

The final API response contains:

```json
{
  "success": true,
  "data": {
    "shiftId": "uuid",
    "payrollId": "uuid",
    "calculation": {
      "segmentPayments": [
        {
          "segment": { "start", "end", "durationMinutes", "dayOfWeekName", "shiftType" },
          "shiftType": "DAY",
          "rate": 1.25,
          "pay": 150.00
        }
      ],
      "sleepoverFlatRateApplied": true,
      "allowanceDetails": [
        { "type": "MEAL", "amount": 15.50, "isEligible": true, "reason": "Shift > 5 hours" }
      ],
      "summary": {
        "basePay": 500.00,
        "overtimePay": 120.00,
        "allowances": 35.50,
        "totalPay": 655.50,
        "totalPaidMinutes": 480
      },
      "tax": { /* see 11.5 */ },
      "periodSummary": {
        "periodType": "Weekly",
        "threshold": 38,
        "priorHours": 30,
        "totalHours": 42,
        "normalHours": 38,
        "overtimeHours": 4,
        "normalPay": 760.00,
        "overtimePay": 120.00,
        "totalPay": 915.50,
        "overtimeRate": 1.5,
        "formula": { /* human-readable explanation */ },
        "tax": { /* formatted tax breakdown */ }
      }
    }
  }
}
```

### 12.1 Formula Object (Human-Readable)
```json
{
  "threshold": "38 hours per week",
  "overtimeRule": "Hours > 38 are overtime",
  "rate": "Normal: 1.25x, Overtime: 1.5x / 2.0x",
  "calculation": "Total Hours: 42h = Normal: 38h + Overtime: 4h",
  "payBreakdown": "Base Rate: $25, Multiplier: 1.25x (Effective: $31.25), Normal Pay: $760, Overtime: $120, Allowances: $35.50, Total Gross: $915.50, Tax Withheld: $152.42, Net Pay: $792.58"
}
```

---

## 13. Key Constants & Fallbacks

| Constant | Value |
|----------|-------|
| SLEEPOVER_FLAT_RATE_DEFAULT | `$60.02` |
| DEFAULT_WEEKLY_THRESHOLD | `38` hours |
| DEFAULT_FORTNIGHTLY_THRESHOLD | `76` hours |
| DEFAULT_MONTHLY_THRESHOLD | `152` hours |
| DEFAULT_PAYMENT_FREQUENCY | `WEEKLY` (value = 2) |
| DEFAULT_DAILY_OVERTIME_THRESHOLD | `10` hours (24h window) |
| SCHADS Casual Multipliers | DAY=1.25, AFTERNOON=1.375, NIGHT=1.4, SAT=1.75, SUN=2.25, PH=2.75, OT=1.75, OT_L2=2.25 |
| SCHADS Permanent Multipliers | DAY=1.0, AFTERNOON=1.125, NIGHT=1.15, SAT=1.5, SUN=2.0, PH=2.5, OT=1.5, OT_L2=2.0 |
| LAUNDRY_ANNUAL_TAX_FREE | `$150` |
| KM_TRAVEL_TAX_FREE_RATE | `$0.85/km` (max 5,000 km) |
| MEAL_ALLOWANCE_REASONABLE_LIMIT | `$35.65` per occasion |

---

## 13b. Sleep Disturbances (Detailed)

### 13.1 Eligibility
- Sleep disturbance pay is only calculated when:
  1. `sleepoverConfiguration.enabled = true`
  2. `sleepoverConfiguration.enableDisturbance = true` (requires `MIN_SLEEP_DISTURBANCE_HOURS` rule)
  3. The shift has sleepover flat rate applied

### 13.2 Validation
Disturbances must fall **completely within the sleepover period**:
```
invalid if (disturbanceEnd <= sleepoverStart) OR (disturbanceStart >= sleepoverEnd)
```

### 13.3 Minimum Duration Rule
Each disturbance is rounded up to a minimum duration:
```ts
minDurationHours = rule MIN_SLEEP_DISTURBANCE_HOURS ?? 1 hour
if (rawDurationMinutes < minDurationHours * 60) {
  chargedMinutes = minDurationHours * 60;  // rounded up
} else {
  chargedMinutes = rawDurationMinutes;
}
```

### 13.4 Pay Calculation
```ts
overtimeMultiplier = getShiftTypeMultiplier('OVERTIME', shiftDefinitions, employmentType, isRemote);
rate = baseRate * overtimeMultiplier;
totalPay = (totalChargedMinutes / 60) * rate;
```
All disturbances are aggregated and paid at the **overtime rate**.

---

## 14. Weekly Hours Calculation (Detailed)

### 14.1 What It Does
`calculateWeeklyHours` scans all `ShiftSegment` records for a tenant and aggregates:
- `weeklyHours` — WORK segments within the current week
- `fortnightlyHours` — WORK segments within the current fortnight
- `monthlyHours` — WORK segments within the current month
- `dailyOvertimeHours` — hours exceeding `OVERTIME_AFTER_HOURS` per calendar day
- `weeklyOvertimeHours` — hours exceeding `MAX_WEEKLY_HOURS`
- `fortnightlyOvertimeHours` — hours exceeding `MAX_FORTNIGHT_HOURS`
- `monthlyOvertimeHours` — hours exceeding `MAX_MONTHLY_HOURS`
- `sleepovrHours` — sleepover hours (prefix/suffix logic for flat rate)
- `disturbanceHours` — disturbance segment hours
- `laundryPaid` / `uniformPaid` — weekly allowance caps

### 14.2 Sleepover Hours Logic
When a sleepover segment qualifies for flat rate:
- Only prefix work (before sleepover window) and suffix work (after sleepover window) count toward weekly/fortnightly/monthly hours.
- The sleepover hours themselves are tracked separately in `sleepovrHours`.
- Disturbance hours are tracked separately in `disturbanceHours`.

### 14.3 Locking
The `payrollHours` record is locked after the period ends:
```ts
shouldLock = now > periodEnd;
// Fortnightly: now > fortnightEnd
// Monthly: now > monthEnd
// Weekly/Daily: now > weekEnd
```
Once locked, the record is **not updated** by subsequent `calculateWeeklyHours` runs.

### 14.4 Prior Hours for New Shifts
Before processing a new shift, the controller:
1. Refreshes the weekly hours cache via `calculateWeeklyHours`.
2. Fetches the current `payrollHours` record for the staff member.
3. Uses `weeklyHours`, `fortnightlyHours`, `monthlyHours` as `priorPeriodicHours`.

---

## 15. Tax Calculation — ATO Formula (Detailed)

### 15.1 ATO Scale 2 Formula
The Australian PAYG withholding uses a **linear formula** per bracket:
```
y = (a x x) - b
```
Where:
- `x` = weekly earnings figure (adjusted per frequency)
- `a` = coefficient A (cents per dollar)
- `b` = coefficient B (base amount)
- `y` = weekly tax withheld

### 15.2 Frequency Conversion (NAT 1008)

| Frequency | x Calculation | Multiplier | Rounding |
|-----------|--------------|------------|----------|
| **Weekly** | `x = floor(gross) + 0.99` | 1 | Round to nearest dollar |
| **Fortnightly** | `x = floor(gross / 2) + 0.99` | 2 | Truncate weekly tax, then `x 2`, ignore cents |
| **Monthly** | `x = floor(gross x 3 / 13) + 0.99` | 13/3 | If gross ends in `.33`, add `.01` first; truncate weekly tax, then `x 13/3`, round to nearest dollar |

### 15.3 Example (Weekly)
```
Gross = $1,104.10
x = floor(1104.10) + 0.99 = 1104.99
Bracket: lessThan=1282, a=0.3227, b=180.0385
y = (0.3227 x 1104.99) - 180.0385 = 176.54
Tax Withheld = round(176.54) = $177
Net Pay = 1104.10 - 177 = $927.10
```

### 15.4 Bracket Lookup
Brackets are stored in `tax_bracket` table per tenant, year, and frequency:
```ts
interface AtoBracket {
  lessThan: number | null;  // upper bound (exclusive), null = top bracket
  a: number;                // coefficient A
  b: number;                // coefficient B
}
```

### 15.5 Allowance Tax Treatment Recap

| Allowance | Tax-Free Limit | Taxable Excess |
|-----------|---------------|----------------|
| Laundry / Uniform | $150/year | Yes |
| KM Travel | $0.85/km (max 5,000 km) | Yes |
| Overtime Meal | $35.65 per occasion | Yes |
| Domestic Travel | $335/day | Yes |
| Broken Shift | None | Fully taxable |
| Task / Skill | None | Fully taxable |

---

## 16. Minimum Engagement Rule (Detailed)

### 16.1 Rule Lookup
```ts
minEngagementRule =
  rules.find('MIN_ENGAGEMENT_HOURS_SOC_COMM') OR
  rules.find('MIN_ENGAGEMENT_HOURS_HOME_DISABILITY')
minEngagementMinutes = rule.value ? rule.value * 60 : 120;  // default 2 hours
```

### 16.2 Gap Calculation
```ts
totalWorkDuration = sum of all non-sleepover, non-PAID_GAP_TIME segment durations
if (totalWorkDuration < minEngagementMinutes) {
  gapMinutes = minEngagementMinutes - totalWorkDuration;
  append PAID_GAP_TIME segment after last work block;
}
```

### 16.3 Exception: Sleepover Continuation
If a work block immediately follows a sleepover block, **no gap time is added** (treated as a single continuous engagement).

---

## 17. Evening Trigger Rule (Detailed)

### 17.1 Trigger Condition
On **weekdays**, if the **physical shift end time** (in local timezone) is **>= evening start hour** (default: 20:00 / 8 PM, from AFTERNOON definition startTime):
- All preceding `DAY` segments in the same engagement are upgraded to `AFTERNOON`.

### 17.2 Morning Reset
The upgrade is reset at the **DAY definition start time** (default: 06:00). Segments starting at or after the morning reset are not upgraded.

### 17.3 Example
- Shift: 18:00–21:00 on a Tuesday
- Without evening trigger: 18:00–20:00 = DAY (1.0x), 20:00–21:00 = AFTERNOON (1.125x)
- With evening trigger: entire 18:00–21:00 = AFTERNOON (1.125x) because shift ends after 20:00

---

## 18. Complete Source File Map

| File | Purpose |
|------|---------|
| `pricing-service/src/controller/payroll.controller.ts` | HTTP entry point, orchestrates all 7 stages |
| `pricing-service/src/service/payroll/engine/payrollEngine.ts` | Main orchestrator (`processShift`) |
| `pricing-service/src/service/payroll/shiftSegmentation.service.ts` | Splits shift by definitions, midnight, sleepover windows |
| `pricing-service/src/service/payroll/shiftTypeResolution.service.ts` | Resolves segment types, applies overtime triggers, weekend vs overtime comparison |
| `pricing-service/src/service/payroll/payCalculation.service.ts` | Calculates segment pay, sleepover flat rate, total pay |
| `pricing-service/src/util/weeklyOvertime.util.ts` | Weekly/fortnightly/monthly overtime data + pay math |
| `pricing-service/src/service/payroll/allowanceCalculation.service.ts` | Laundry, uniform, meal, km travel, sleepover allowances |
| `pricing-service/src/service/brokenShift.service.ts` | Broken shift sequence (shift 2 & 3 of day) + allowance lookup |
| `pricing-service/src/service/payroll/taxCalculation.service.ts` | PAYG withholding: line items, bracket formula, per-item breakdown |
| `pricing-service/src/util/payroll/taxCalculation.util.ts` | Pure ATO Scale 2 formula implementation (NAT 1008) |
| `pricing-service/src/service/payroll/tenantConfig.service.ts` | Loads tenant config (rules, definitions, allowances, holidays) |
| `pricing-service/src/service/payroll/sleepDisturbance.service.ts` | Validates, normalizes, and calculates sleep disturbance pay |
| `pricing-service/src/service/weeklyHours.service.ts` | Aggregates weekly/fortnightly/monthly/daily hours per staff |
| `pricing-service/src/service/payroll/rules/minimumEngagement.rule.ts` | Calculates minimum engagement gap |
| `pricing-service/src/service/payroll/rules/eveningTrigger.rule.ts` | Upgrades DAY -> AFTERNOON when shift ends past evening hour |

---

## 19. Section Summary

| Section | Content |
|---------|---------|
| 1. High-Level Flow | 7-stage pipeline diagram |
| 2. Input Parameters | All 13 request fields with types |
| 3. Configuration Loading | Tenant config: rules, shift definitions, allowances, holidays |
| 4. Shift Segmentation | Time-based splitting, sleepover handling, minimum engagement |
| 5. Shift Type Resolution | Priority stack, 5 overtime triggers, rate comparison |
| 6. Pay Calculation | Segment formula, sleepover flat rate, effective base rate |
| 7. Overtime Calculation | Daily/weekly/fortnightly/monthly thresholds, L1/L2 tiers |
| 8. Allowances | Laundry, uniform, meal, km travel, sleepover |
| 9. Broken Shift Allowance | Shift 2 & 3 of day sequence rule |
| 10. Sleep Disturbances | Eligibility, validation, minimum duration, pay at OT rate |
| 11. Tax Calculation (PAYG) | ATO Scale 2, per-item breakdown, net pay |
| 12. Summary Response Structure | Full JSON shape + formula object |
| 13. Key Constants & Fallbacks | All SCHADS multipliers, tax-free limits |
| 14-17. Deep Dives | Sleep disturbances, weekly hours aggregation, ATO formula (NAT 1008), minimum engagement, evening trigger |
| 18. Source File Map | All 15 files with exact paths |
