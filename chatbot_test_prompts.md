# Chatbot Test Prompts for Shift Data

## Prompt 1: Calculate Pay for Single Shift
```
Calculate the pay for this shift:
- Worker: Chidinma AGANAMA
- Position: Disability Support Worker
- Start: 02 Dec 2025 5:00 PM
- End: 03 Dec 2025 9:00 AM
- Hours: 5.00
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Evening rate

Please show the breakdown of segments, multipliers used, and total pay.
```

**Expected Answer:**
```
Shift Breakdown:
- Total shift: 02 Dec 2025 5:00 PM to 03 Dec 2025 9:00 AM (16 hours)
- This is an overnight shift that spans multiple rate periods

Segment Breakdown:
1. 17:00-20:00 (3h) - WEEKDAY - AFTERNOON rate (1.375x)
2. 20:00-24:00 (4h) - WEEKDAY - AFTERNOON rate (1.375x)
3. 00:00-06:00 (6h) - WEEKDAY - NIGHT rate (1.40x)
4. 06:00-09:00 (3h) - WEEKDAY - DAY rate (1.25x)

However, this is a pre-segmented entry showing only the Evening rate portion:
- Evening rate portion: 5.00 hours
- Multiplier: 1.375x (SCHADS AFTERNOON rate)
- Calculation: 5.00 × $34.58 × 1.375 = $237.74

Total Pay: $237.74
```

## Prompt 2: Calculate Pay for Normal Rate Shift
```
Calculate the pay for this shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 05 Dec 2025 6:00 AM
- End: 05 Dec 2025 2:00 PM
- Hours: 8.00
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Normal rate

Please show the calculation breakdown.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 05 Dec 2025 6:00 AM to 05 Dec 2025 2:00 PM (8 hours)
- Day: Friday (WEEKDAY)
- Rate type: Normal rate (DAY)

Segment Breakdown:
- Single segment: 06:00-14:00 (8h) - WEEKDAY - DAY rate (1.25x)

Calculation:
- Hours: 8.00
- Base rate: $34.58/hr
- Multiplier: 1.25x (casual DAY rate)
- Pay: 8.00 × $34.58 × 1.25 = $345.80

Total Pay: $345.80
```

## Prompt 3: Calculate Pay for Sunday Rate Shift
```
Calculate the pay for this shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 06 Dec 2025 9:30 PM
- End: 07 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Sunday rate

Please explain how the Sunday rate is applied and show the segment breakdown.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 06 Dec 2025 9:30 PM to 07 Dec 2025 6:30 AM (9 hours)
- Spans: Saturday night to Sunday morning
- Rate type: Sunday rate

Segment Breakdown:
1. 21:30-24:00 (2.5h) - SATURDAY - SATURDAY rate (1.75x)
2. 00:00-06:30 (6.5h) - SUNDAY - SUNDAY rate (2.25x)

This is a pre-segmented entry showing only the Sunday rate portion:
- Sunday rate portion: 6.00 hours
- Multiplier: 2.25x (SCHADS SUNDAY rate)
- Calculation: 6.00 × $34.58 × 2.25 = $466.83

Total Pay: $466.83

Note: The shift spans Saturday night, but this entry only accounts for the Sunday portion.
```

## Prompt 4: Calculate Pay for Night Rate Shift
```
Calculate the pay for this shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 07 Dec 2025 9:30 PM
- End: 08 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Night rate

Please show how the night rate is calculated and any segment splits.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 07 Dec 2025 9:30 PM to 08 Dec 2025 6:30 AM (9 hours)
- Spans: Sunday night to Monday morning
- Rate type: Night rate

Segment Breakdown:
1. 21:30-24:00 (2.5h) - SUNDAY - SUNDAY rate (2.25x)
2. 00:00-06:00 (6h) - WEEKDAY - NIGHT rate (1.40x)
3. 06:00-06:30 (0.5h) - WEEKDAY - DAY rate (1.25x)

This is a pre-segmented entry showing only the Night rate portion:
- Night rate portion: 6.00 hours
- Multiplier: 1.40x (SCHADS NIGHT rate)
- Calculation: 6.00 × $34.58 × 1.40 = $290.47

Total Pay: $290.47

Note: The shift spans Sunday night to Monday morning, but this entry only accounts for the Night portion.
```

## Prompt 5: Calculate Pay for Saturday Rate Shift
```
Calculate the pay for this shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 06 Dec 2025 9:30 PM
- End: 07 Dec 2025 6:30 AM
- Hours: 2.50
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Saturday rate

Please explain the Saturday rate application.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 06 Dec 2025 9:30 PM to 07 Dec 2025 6:30 AM (9 hours)
- Spans: Saturday night to Sunday morning
- Rate type: Saturday rate

Segment Breakdown:
1. 21:30-24:00 (2.5h) - SATURDAY - SATURDAY rate (1.75x)
2. 00:00-06:30 (6.5h) - SUNDAY - SUNDAY rate (2.25x)

This is a pre-segmented entry showing only the Saturday rate portion:
- Saturday rate portion: 2.50 hours
- Multiplier: 1.75x (SCHADS SATURDAY rate)
- Calculation: 2.50 × $34.58 × 1.75 = $151.29

Total Pay: $151.29

Note: The shift spans Saturday night to Sunday morning, but this entry only accounts for the Saturday portion.
```

## Prompt 6: Verify Evening Rate Calculation
```
I need to verify the evening rate calculation:
- Worker: Samantha MACUMBER
- Position: Disability Support Worker
- Start: 09 Dec 2025 5:00 PM
- End: 10 Dec 2025 9:00 AM
- Hours: 5.00
- Base rate: $34.58/hr
- Employment type: Casual
- Expected amount: $237.74

Please calculate and confirm if this matches. Show the multiplier used.
```

**Expected Answer:**
```
Verification Result: ✅ CORRECT

Calculation:
- Hours: 5.00
- Base rate: $34.58/hr
- Multiplier: 1.375x (SCHADS AFTERNOON rate, not 1.38x)
- Pay: 5.00 × $34.58 × 1.375 = $237.74

The expected amount of $237.74 matches the calculation.

Important Note: The rate description says "Evening rate (casual)" with 1.38x, but the actual SCHADS standard multiplier for AFTERNOON rate is 1.375x. The system correctly uses 1.375x.
```

## Prompt 7: Calculate Pay for 9-Hour Normal Shift
```
Calculate the pay for this shift:
- Worker: Samantha MACUMBER
- Position: Disability Support Worker
- Start: 11 Dec 2025 9:00 AM
- End: 11 Dec 2025 6:00 PM
- Hours: 9.00
- Base rate: $34.58/hr
- Employment type: Casual
- Rate type: Normal rate

Please show the calculation and confirm the expected amount is $389.03.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 11 Dec 2025 9:00 AM to 11 Dec 2025 6:00 PM (9 hours)
- Day: Thursday (WEEKDAY)
- Rate type: Normal rate

Segment Breakdown:
- Single segment: 09:00-18:00 (9h) - WEEKDAY - DAY rate (1.25x)

Calculation:
- Hours: 9.00
- Base rate: $34.58/hr
- Multiplier: 1.25x (casual DAY rate)
- Pay: 9.00 × $34.58 × 1.25 = $389.025 → $389.03 (rounded)

Verification: ✅ CORRECT
Expected amount $389.03 matches the calculation.

Total Pay: $389.03
```

## Prompt 8: Test Overnight Shift with Multiple Rates
```
Calculate the pay for this overnight shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 13 Dec 2025 9:30 PM
- End: 14 Dec 2025 6:30 AM
- Base rate: $34.58/hr
- Employment type: Casual

This shift spans Saturday night to Sunday morning. Please show:
1. How the shift is segmented
2. What rates apply to each segment
3. The total pay calculation
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 13 Dec 2025 9:30 PM to 14 Dec 2025 6:30 AM (9 hours)
- Spans: Saturday night to Sunday morning

Segment Breakdown:
1. 21:30-24:00 (2.5h) - SATURDAY - SATURDAY rate (1.75x)
   - Pay: 2.5 × $34.58 × 1.75 = $151.29

2. 00:00-06:30 (6.5h) - SUNDAY - SUNDAY rate (2.25x)
   - Pay: 6.5 × $34.58 × 2.25 = $505.73

Total Pay: $151.29 + $505.73 = $657.02

Note: This is the complete shift calculation. The data has this split into separate entries:
- 6.00h Sunday rate: $466.83
- 0.50h Sunday rate: $38.90
- 2.50h Saturday rate: $151.29
Total: $657.02
```

## Prompt 9: Verify Sunday Rate Calculation
```
Please verify this Sunday rate calculation:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 13 Dec 2025 9:30 PM
- End: 14 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Employment type: Casual
- Expected amount: $466.83

Show the calculation: 6.00 × $34.58 × 2.25 = $466.83
```

**Expected Answer:**
```
Verification Result: ✅ CORRECT

Calculation:
- Hours: 6.00
- Base rate: $34.58/hr
- Multiplier: 2.25x (SCHADS SUNDAY rate)
- Pay: 6.00 × $34.58 × 2.25 = $466.83

Formula: 6.00 × $34.58 × 2.25 = $466.83

The expected amount of $466.83 matches the calculation exactly.

Total Pay: $466.83
```

## Prompt 10: Test Allowance Calculation
```
How do I calculate the KM allowance for this shift?
- Worker: Chidinma AGANAMA
- Allowance type: KM Allowance
- Description: From 44 Dianchi drive, Wyndham Vale to Manor lakes shopping center. This travel was ×2
- Quantity: 2.0 km
- Status: Approved

Please explain the KM allowance calculation rate.
```

**Expected Answer:**
```
KM Allowance Calculation:

- Allowance type: KM Allowance
- Quantity: 2.0 km
- Rate: $0.99 per km (SCHADS standard)
- Calculation: 2.0 × $0.99 = $1.98

Note: The data shows the quantity as 2.0 km, but the actual dollar amount is not provided in the timesheet format. Allowances are typically calculated separately from timesheet pay.

KM Allowance Rate: $0.99/km
Total Allowance: $1.98
```

## Prompt 11: Test Sleepover Allowance
```
How is the sleepover allowance calculated?
- Worker: Samantha MACUMBER
- Allowance type: Sleepover Allowance
- Description: Sleep over allowance (fixed amount)
- Quantity: 1.0
- Status: Approved

Please explain the sleepover allowance flat rate.
```

**Expected Answer:**
```
Sleepover Allowance Calculation:

- Allowance type: Sleepover Allowance
- Description: Sleep over allowance (fixed amount)
- Quantity: 1.0 (unit)
- Flat rate: $60.02 (SCHADS standard)

Calculation:
- Sleepover allowance is a fixed flat rate, not calculated by hours
- Rate: $60.02 per sleepover
- Total: $60.02

Note: This is a fixed amount allowance, not dependent on hours worked. The quantity "1.0" indicates one sleepover shift.
```

## Prompt 12: Test Sleep Disturbance Allowance
```
How is the sleep disturbance allowance calculated?
- Worker: Samantha MACUMBER
- Allowance type: Sleep Disturbance
- Description: Sleep disturbance allowance 0.72 hours
- Quantity: 8.0
- Status: Approved

Please explain the sleep disturbance calculation.
```

**Expected Answer:**
```
Sleep Disturbance Allowance Calculation:

- Allowance type: Sleep Disturbance
- Description: Sleep disturbance allowance 0.72 hours
- Quantity: 8.0 (units)

Calculation:
- Sleep disturbance is paid at overtime rate
- Base rate: $34.58/hr
- Overtime multiplier: 1.75x (casual)
- Rate: $34.58 × 1.75 = $60.515/hr
- Total: 8.0 × $60.515 = $484.12

Note: The quantity 8.0 appears to be the number of disturbance units, not hours. The actual calculation depends on the specific disturbance duration and rate rules.
```

## Prompt 13: Comprehensive Shift Test
```
Please calculate the total pay for this complete shift:
- Worker: Kimiya PARANGASA
- Position: Disability Support Worker
- Start: 20 Dec 2025 9:30 PM
- End: 21 Dec 2025 6:30 AM
- Base rate: $34.58/hr
- Employment type: Casual

The shift has these segments:
- 0.50 hours at Sunday rate (2.25x)
- 2.50 hours at Saturday rate (1.75x)
- 6.00 hours at Sunday rate (2.25x)

Please verify the total calculation matches the expected amounts.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 20 Dec 2025 9:30 PM to 21 Dec 2025 6:30 AM (9 hours)
- Spans: Saturday night to Sunday morning

Segment Breakdown:
1. 21:30-24:00 (2.5h) - SATURDAY - SATURDAY rate (1.75x)
   - Pay: 2.5 × $34.58 × 1.75 = $151.29

2. 00:00-06:30 (6.5h) - SUNDAY - SUNDAY rate (2.25x)
   - Pay: 6.5 × $34.58 × 2.25 = $505.73

Pre-segmented entries verification:
- 0.50h Sunday rate: 0.50 × $34.58 × 2.25 = $38.90 ✅
- 2.50h Saturday rate: 2.50 × $34.58 × 1.75 = $151.29 ✅
- 6.00h Sunday rate: 6.00 × $34.58 × 2.25 = $466.83 ✅

Total from segments: $38.90 + $151.29 + $466.83 = $657.02
Total from complete shift: $151.29 + $505.73 = $657.02

Verification: ✅ MATCH
```

## Prompt 14: Batch Calculation Request
```
Please calculate the pay for these 3 shifts:

Shift 1:
- Worker: Kimiya PARANGASA
- Start: 12 Dec 2025 6:00 AM
- End: 12 Dec 2025 2:00 PM
- Hours: 8.00
- Base rate: $34.58/hr
- Casual employment
- Normal rate

Shift 2:
- Worker: Kimiya PARANGASA
- Start: 19 Dec 2025 6:00 AM
- End: 19 Dec 2025 2:00 PM
- Hours: 8.00
- Base rate: $34.58/hr
- Casual employment
- Normal rate

Shift 3:
- Worker: Kimiya PARANGASA
- Start: 14 Dec 2025 9:30 PM
- End: 15 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Casual employment
- Night rate

Show the calculation for each and the total.
```

**Expected Answer:**
```
Shift 1 Calculation:
- Time: 12 Dec 2025 6:00 AM to 12 Dec 2025 2:00 PM (8 hours)
- Day: Friday (WEEKDAY)
- Rate: Normal rate (1.25x)
- Pay: 8.00 × $34.58 × 1.25 = $345.80

Shift 2 Calculation:
- Time: 19 Dec 2025 6:00 AM to 19 Dec 2025 2:00 PM (8 hours)
- Day: Friday (WEEKDAY)
- Rate: Normal rate (1.25x)
- Pay: 8.00 × $34.58 × 1.25 = $345.80

Shift 3 Calculation:
- Time: 14 Dec 2025 9:30 PM to 15 Dec 2025 6:30 AM (9 hours)
- Spans: Sunday night to Monday morning
- Rate: Night rate (1.40x) - pre-segmented portion
- Pay: 6.00 × $34.58 × 1.40 = $290.47

Total Pay: $345.80 + $345.80 + $290.47 = $982.07
```

## Prompt 15: Rate Multiplier Verification
```
Please confirm the SCHADS casual multipliers for these rate types:
- Normal rate
- Evening/Afternoon rate
- Night rate
- Saturday rate
- Sunday rate

For each multiplier, show:
1. The standard multiplier value
2. The calculation formula
3. An example calculation with $34.58 base rate
```

**Expected Answer:**
```
SCHADS Casual Multipliers:

1. Normal rate (DAY)
   - Standard multiplier: 1.25x
   - Formula: hours × base_rate × 1.25
   - Example: 8.00 × $34.58 × 1.25 = $345.80

2. Evening/Afternoon rate (AFTERNOON)
   - Standard multiplier: 1.375x
   - Formula: hours × base_rate × 1.375
   - Example: 5.00 × $34.58 × 1.375 = $237.74
   - Note: Often labeled as 1.38x but actual is 1.375x

3. Night rate (NIGHT)
   - Standard multiplier: 1.40x
   - Formula: hours × base_rate × 1.40
   - Example: 6.00 × $34.58 × 1.40 = $290.47

4. Saturday rate (SATURDAY)
   - Standard multiplier: 1.75x
   - Formula: hours × base_rate × 1.75
   - Example: 2.50 × $34.58 × 1.75 = $151.29

5. Sunday rate (SUNDAY)
   - Standard multiplier: 2.25x
   - Formula: hours × base_rate × 2.25
   - Example: 6.00 × $34.58 × 2.25 = $466.83
```

## Prompt 16: Edge Case Test - Short Shift
```
Calculate the pay for this short shift:
- Worker: Kimiya PARANGASA
- Start: 06 Dec 2025 9:30 PM
- End: 07 Dec 2025 6:30 AM
- Hours: 0.50
- Base rate: $34.58/hr
- Casual employment
- Sunday rate

Expected: $38.90
Calculation: 0.50 × $34.58 × 2.25 = $38.90

Please verify and explain any minimum engagement rules.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 06 Dec 2025 9:30 PM to 07 Dec 2025 6:30 AM (9 hours)
- Pre-segmented portion: 0.50 hours
- Rate: Sunday rate (2.25x)

Calculation:
- Hours: 0.50
- Base rate: $34.58/hr
- Multiplier: 2.25x
- Pay: 0.50 × $34.58 × 2.25 = $38.90

Verification: ✅ CORRECT
Expected: $38.90
Calculated: $38.90

Minimum Engagement Rule:
- SCHADS minimum engagement: 2 hours (120 minutes)
- This is a pre-segmented portion of a larger shift, so minimum engagement does not apply to this segment individually
- The complete shift (9 hours) exceeds the minimum engagement requirement

Total Pay: $38.90
```

## Prompt 17: Edge Case Test - Long Shift
```
Calculate the pay for this long shift:
- Worker: Samantha MACUMBER
- Start: 11 Dec 2025 9:00 AM
- End: 11 Dec 2025 6:00 PM
- Hours: 9.00
- Base rate: $34.58/hr
- Casual employment
- Normal rate

Expected: $389.03
Calculation: 9.00 × $34.58 × 1.25 = $389.03

Please verify and check if any overtime applies.
```

**Expected Answer:**
```
Shift Breakdown:
- Time: 11 Dec 2025 9:00 AM to 11 Dec 2025 6:00 PM (9 hours)
- Day: Thursday (WEEKDAY)
- Rate: Normal rate (1.25x)

Calculation:
- Hours: 9.00
- Base rate: $34.58/hr
- Multiplier: 1.25x
- Pay: 9.00 × $34.58 × 1.25 = $389.025 → $389.03 (rounded)

Verification: ✅ CORRECT
Expected: $389.03
Calculated: $389.03

Overtime Check:
- Daily overtime threshold: 10 hours
- This shift: 9 hours
- Overtime does not apply (9 < 10)

Total Pay: $389.03
```

## Prompt 18: Compare Two Similar Shifts
```
Compare these two shifts and explain any differences:

Shift A:
- Worker: Kimiya PARANGASA
- Start: 06 Dec 2025 9:30 PM
- End: 07 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Casual employment
- Sunday rate

Shift B:
- Worker: Kimiya PARANGASA
- Start: 13 Dec 2025 9:30 PM
- End: 14 Dec 2025 6:30 AM
- Hours: 6.00
- Base rate: $34.58/hr
- Casual employment
- Sunday rate

Both should calculate to $466.83. Please confirm.
```

**Expected Answer:**
```
Shift Comparison:

Shift A:
- Date: 06-07 Dec 2025 (Saturday night to Sunday morning)
- Hours: 6.00
- Rate: Sunday rate (2.25x)
- Pay: 6.00 × $34.58 × 2.25 = $466.83

Shift B:
- Date: 13-14 Dec 2025 (Saturday night to Sunday morning)
- Hours: 6.00
- Rate: Sunday rate (2.25x)
- Pay: 6.00 × $34.58 × 2.25 = $466.83

Comparison Result: ✅ IDENTICAL
Both shifts have the same:
- Duration (6 hours)
- Rate type (Sunday rate)
- Multiplier (2.25x)
- Base rate ($34.58/hr)
- Total pay ($466.83)

The calculations match exactly as expected.
```

## Prompt 19: Test All Rate Types
```
Please calculate the pay for these shifts, each with a different rate type:

1. Normal rate: 8 hours at $34.58/hr (casual)
2. Evening rate: 5 hours at $34.58/hr (casual)
3. Night rate: 6 hours at $34.58/hr (casual)
4. Saturday rate: 2.5 hours at $34.58/hr (casual)
5. Sunday rate: 6 hours at $34.58/hr (casual)

Show the multiplier used for each and the final amount.
```

**Expected Answer:**
```
All Rate Types Calculation:

1. Normal rate (1.25x)
   - Hours: 8.00
   - Calculation: 8.00 × $34.58 × 1.25 = $345.80

2. Evening rate (1.375x)
   - Hours: 5.00
   - Calculation: 5.00 × $34.58 × 1.375 = $237.74

3. Night rate (1.40x)
   - Hours: 6.00
   - Calculation: 6.00 × $34.58 × 1.40 = $290.47

4. Saturday rate (1.75x)
   - Hours: 2.50
   - Calculation: 2.50 × $34.58 × 1.75 = $151.29

5. Sunday rate (2.25x)
   - Hours: 6.00
   - Calculation: 6.00 × $34.58 × 2.25 = $466.83

Summary:
- Normal: $345.80 @ 1.25x
- Evening: $237.74 @ 1.375x
- Night: $290.47 @ 1.40x
- Saturday: $151.29 @ 1.75x
- Sunday: $466.83 @ 2.25x
```

## Prompt 20: Verification Summary Request
```
I have 28 shift entries to verify. Can you help me create a verification checklist for:
1. Timesheet calculations (24 entries)
2. Allowance calculations (4 entries)

For each type, please list:
- What to verify
- Common issues to check
- Expected calculation formula
- Acceptable tolerance for rounding differences
```

**Expected Answer:**
```
Verification Checklist for 28 Shift Entries

TIMESHEET CALCULATIONS (24 entries):

What to Verify:
- [ ] Hours × Base Rate × Multiplier = Amount
- [ ] Multiplier matches SCHADS standard for rate type
- [ ] Rounding is consistent (half-up to nearest cent)
- [ ] Segment breakdown matches time periods

Common Issues to Check:
- [ ] Evening rate uses 1.375x (not 1.38x)
- [ ] Overnight shifts are segmented at midnight
- [ ] Weekend rates apply correctly (Saturday/Sunday)
- [ ] Night rate applies to 00:00-06:00 period
- [ ] Minimum engagement (2 hours) is applied if needed

Expected Calculation Formula:
Amount = Hours × Base Rate × Multiplier

Acceptable Tolerance:
- Exact Match: Difference < $0.01
- Acceptable: Difference < $0.05
- Review Required: Difference > $0.05

ALLOWANCE CALCULATIONS (4 entries):

What to Verify:
- [ ] Allowance type matches description
- [ ] Quantity is correct
- [ ] Status is "Approved"
- [ ] Fixed amounts use correct flat rates

Common Issues to Check:
- [ ] Sleepover allowance uses $60.02 flat rate
- [ ] KM allowance uses $0.99/km rate
- [ ] Sleep disturbance uses overtime rate
- [ ] Allowance amounts are separate from timesheet pay

Expected Calculation:
- Fixed allowances: Use flat rate
- Quantity-based: Quantity × Rate

Acceptable Tolerance:
- Fixed amounts must match exactly
- Quantity-based: Difference < $0.01
```

## Usage Instructions

### How to Use These Prompts

1. **Single Shift Testing**: Use Prompts 1-7 for individual shift verification
2. **Rate Type Testing**: Use Prompts 8-13 for specific rate scenarios
3. **Batch Testing**: Use Prompt 14 for multiple shifts
4. **Reference**: Use Prompt 15 for multiplier reference
5. **Edge Cases**: Use Prompts 16-17 for boundary testing
6. **Comparison**: Use Prompt 18 for similar shift comparison
7. **Comprehensive**: Use Prompt 19 for all rate types
8. **Planning**: Use Prompt 20 for verification planning

### Expected Responses

For each calculation, the chatbot should provide:
- Segment breakdown (if applicable)
- Multiplier used with explanation
- Calculation formula
- Final amount
- Any special rules applied (minimum engagement, overtime, etc.)

### Verification Criteria

- **Exact Match**: Difference < $0.01
- **Acceptable**: Difference < $0.05
- **Review Required**: Difference > $0.05

### Common Issues to Check

1. **Evening Rate**: Verify 1.375x (not 1.38x) is used
2. **Rounding**: Check rounding method (half-up vs half-even)
3. **Segmentation**: Verify overnight shifts are split correctly
4. **Minimum Engagement**: Check if 2-hour minimum applies
5. **Overtime**: Verify thresholds (10h daily, 38h weekly)
