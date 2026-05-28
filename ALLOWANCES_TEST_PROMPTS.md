# SCHADS Allowances - Test Prompts

## Module 1: Broken Shift Allowances (Clause 25.6)

### Test 1.1: Two-Period Broken Shift (Valid)
```
Calculate my pay for a broken shift: 4 hours from 8am to 12pm, then 4 hours from 2pm to 6pm. 
I'm home care level 2 pay point 3, casual.
```
**Expected**:
- Base pay for 8 hours (casual loading applied)
- Broken shift allowance: $20.82
- Total span: 10 hours (within 12-hour limit ✅)

### Test 1.2: Three-Period Broken Shift (Valid)
```
I worked a split shift with three periods: 3 hours 7am-10am, 3 hours 12pm-3pm, and 3 hours 5pm-8pm.
Social community services level 3 pay point 2, permanent.
```
**Expected**:
- Base pay for 9 hours
- Broken shift allowance: $27.56
- Total span: 13 hours... wait, this EXCEEDS 12 hours!
- ❌ Should flag final period as overtime (200%)

### Test 1.3: Broken Shift - 12 Hour Span Breach
```
Calculate pay for 4 hours 6am-10am, then 4 hours 8pm-midnight. Home care casual level 2 PP3.
```
**Expected**:
- Total span: 18 hours (6am to midnight)
- ❌ BREACH: Exceeds 12-hour maximum
- Action: Flag final period (8pm-12am) as overtime 200%
- No broken shift allowance (compliance breach)

### Test 1.4: Broken Shift - Minimum Engagement Breach
```
I worked 1.5 hours 8am-9:30am, then 6 hours 2pm-8pm. Home care level 2 PP2 casual.
```
**Expected**:
- ❌ BREACH: First period (1.5h) below 2-hour minimum for home care
- Action: Underpayment flag
- No broken shift allowance

---

## Module 2: Vehicle & Travel Allowances (Clause 20.7)

### Test 2.1: Vehicle Allowance Only
```
8 hour shift on Monday, drove 45 kilometers between client sites using my own car.
Home care level 3 pay point 1, permanent, $32/hour.
```
**Expected**:
- Base pay: 8h × $32 = $256
- Vehicle allowance: 45km × $0.96 = $43.20
- **Total: $299.20**

### Test 2.2: Vehicle + Travel Time Pay
```
Worked 6 hours direct client care, plus 30 minutes travel time between clients, drove 25km.
Saturday shift, casual, $28/hour base.
```
**Expected**:
- Client care: 6h × $28 × 1.5 (Saturday) × 1.25 (casual) = $315
- Travel time: 0.5h × $28 × 1.5 (Saturday) × 1.25 (casual) = $26.25
- Vehicle allowance: 25km × $0.96 = $24.00
- **Total: $365.25**
- Note: Travel time counts as ordinary hours (paid at penalty rate)

### Test 2.3: High Mileage
```
Community outreach day: 4 hours active work, drove 120km visiting multiple participants.
Permanent, $30/hour, weekday.
```
**Expected**:
- Base pay: 4h × $30 = $120
- Vehicle allowance: 120km × $0.96 = $115.20
- **Total: $235.20**

---

## Module 3: First Aid Allowance (Clause 20.6)

### Test 3.1: Full-Time with First Aid Certificate
```
I'm full-time with a current first aid certificate. Calculate my weekly first aid allowance.
```
**Expected**:
- First aid allowance: $19.76/week (flat rate)

### Test 3.2: Part-Time with First Aid (Under Cap)
```
Worked 20 hours this week, I have a first aid certificate. Part-time, $28/hour.
```
**Expected**:
- Base pay: 20h × $28 = $560
- First aid allowance: 20h × $0.52 = $10.40
- **Total: $570.40**

### Test 3.3: Part-Time with First Aid (Capped)
```
Worked 45 hours this week with first aid certificate. Part-time, $30/hour.
```
**Expected**:
- Base pay: 40h ordinary + 5h overtime (calculation depends on context)
- First aid allowance: 45h × $0.52 = $23.40, but **capped at $19.76**
- ⚠️ Warning: First aid allowance capped at weekly maximum

### Test 3.4: Casual with First Aid
```
8 hour shift, casual, first aid qualified, $28/hour base.
```
**Expected**:
- Base pay: 8h × $28 × 1.25 = $280
- First aid allowance: 8h × $0.52 = $4.16
- **Total: $284.16**

---

## Module 4: On-Call Allowance (Clause 20.11)

### Test 4.1: Weekday On-Call
```
I was on call Monday night from 6pm to 8am Tuesday. Calculate my on-call allowance.
```
**Expected**:
- On-call allowance (weekday): $24.50

### Test 4.2: Weekend On-Call
```
On call Saturday 8pm to Sunday 8am. What's my allowance?
```
**Expected**:
- On-call allowance (weekend): $49.00

### Test 4.3: Public Holiday On-Call
```
Rostered on call for Christmas Day (public holiday), 24-hour period.
```
**Expected**:
- On-call allowance (public holiday): $49.00

### Test 4.4: Multiple On-Call Periods
```
On call Monday night ($24.50), Wednesday night ($24.50), and Saturday night ($49.00).
Calculate total on-call allowances for the week.
```
**Expected**:
- Total on-call allowances: $24.50 + $24.50 + $49.00 = $98.00

---

## Module 5: Meal Allowances (Clause 20.5)

### Test 5.1: Unexpected Overtime (Triggers Meal Allowance)
```
Scheduled 8am-4pm but stayed until 6:30pm (2.5 hours unexpected overtime, no notice given).
Permanent, $30/hour.
```
**Expected**:
- Ordinary hours: 8h × $30 = $240
- Overtime: 2.5h × $30 × 1.5 = $112.50
- Meal allowance: $16.62 (unexpected OT >1 hour, no notice)
- **Total: $369.12**

### Test 5.2: Overtime with Notice (No Meal Allowance)
```
Worked 10 hours today (2 hours overtime), but I was told yesterday I'd need to stay late.
$28/hour permanent.
```
**Expected**:
- Ordinary: 8h × $28 = $224
- Overtime: 2h × $28 × 1.5 = $84
- Meal allowance: $0 (notice given on previous day)
- **Total: $308**

### Test 5.3: Meal with Client (Paid Time)
```
6 hour shift including 1 hour meal with client at a restaurant. Casual $30/hour.
```
**Expected**:
- All 6 hours paid (meal with client cannot be unpaid break)
- Pay: 6h × $30 × 1.25 = $225
- Note: Meal time with client is 100% paid time

### Test 5.4: Short Unexpected Overtime (No Allowance)
```
Stayed 45 minutes late unexpectedly. $28/hour permanent.
```
**Expected**:
- Overtime pay: 0.75h × $28 × 1.5 = $31.50
- Meal allowance: $0 (overtime ≤1 hour)

---

## Module 6: Uniform & Laundry Allowance (Clause 20.2)

### Test 6.1: Uniform Required, Not Provided
```
Employer requires uniform but doesn't provide it. I worked 5 shifts this week. Calculate allowances.
```
**Expected**:
- Uniform allowance: $1.49/week

### Test 6.2: Laundry Allowance (Under Cap)
```
I launder my own uniform. Worked 3 shifts this week.
```
**Expected**:
- Laundry allowance: 3 shifts × $0.32 = $0.96

### Test 6.3: Laundry Allowance (Capped)
```
Laundered my uniform myself, worked 6 shifts this week.
```
**Expected**:
- Laundry allowance: 6 × $0.32 = $1.92, but **capped at $1.49**
- ⚠️ Warning: Laundry allowance capped at weekly maximum

### Test 6.4: Both Uniform and Laundry
```
Uniform required (not provided), I wash it myself, worked 4 shifts.
```
**Expected**:
- Uniform allowance: $1.49
- Laundry allowance: 4 × $0.32 = $1.28
- **Total: $2.77**

---

## Module 7: Enhanced Sleepover Validation

### Test 7.1: Sleepover with 4-Hour Rule (Pass - Before)
```
5 hours active work 4pm-9pm, then sleepover 10pm-6am, then 3 hours 7am-10am.
Home care level 2 PP3 casual.
```
**Expected**:
- Active before: 5 hours ✅ (meets 4-hour minimum)
- Active after: 3 hours
- Sleepover allowance: $60.02
- ✅ Compliance: 4-hour rule satisfied

### Test 7.2: Sleepover with 4-Hour Rule (Pass - After)
```
2 hours 8pm-10pm, sleepover 10pm-6am, then 6 hours active 7am-1pm.
Permanent $30/hour.
```
**Expected**:
- Active before: 2 hours
- Active after: 6 hours ✅ (meets 4-hour minimum)
- Sleepover allowance: $60.02
- ✅ Compliance: 4-hour rule satisfied

### Test 7.3: Sleepover with 4-Hour Rule (FAIL)
```
2 hours 8pm-10pm, sleepover 10pm-6am, 2 hours 7am-9am.
Home care casual level 3 PP1.
```
**Expected**:
- Active before: 2 hours ❌
- Active after: 2 hours ❌
- ❌ COMPLIANCE BREACH: No 4-hour active block on either side
- Sleepover allowance: $0 (INVALID)
- Warning: Sleepover requires minimum 4 continuous active hours on at least ONE side

### Test 7.4: Sleepover with 12-Hour Agreement
```
6 hours 3pm-9pm, sleepover 10pm-6am with 12-hour written agreement, 4 hours 7am-11am.
Permanent $32/hour.
```
**Expected**:
- Active before: 6 hours ✅
- Active after: 4 hours ✅
- Sleepover allowance: $60.02
- Ordinary hours cap: 12 hours (Framework B, not 10)
- ✅ Compliance: Both rules satisfied

---

## Complex Multi-Allowance Scenarios

### Scenario A: The Full Package
```
Monday: 4 hours 8am-12pm, drove 30km, then 4 hours 2pm-6pm (broken shift).
I have first aid certificate, uniform required (I wash it), permanent $30/hour.
```
**Expected**:
- Base pay: 8h × $30 = $240
- Broken shift allowance: $20.82
- Vehicle allowance: 30km × $0.96 = $28.80
- First aid: 8h × $0.52 = $4.16
- Laundry: 1 shift × $0.32 = $0.32
- **Total: $274.10**

### Scenario B: Weekend On-Call + Unexpected Callout
```
On call Saturday night, got called in at 2am for 3 hours unexpected work.
Casual $28/hour, first aid qualified.
```
**Expected**:
- On-call allowance: $49.00 (weekend)
- Callout pay: 3h × $28 × 2.0 (Sunday night) × 1.25 (casual) = $210
- First aid: 3h × $0.52 = $1.56
- Meal allowance: $16.62 (unexpected work >1 hour)
- **Total: $277.18**

### Scenario C: Sleepover + Broken Shift + Vehicle
```
Tuesday: 5 hours 3pm-8pm, sleepover 10pm-6am, 3 hours 7am-10am.
Drove 40km between clients during the day shift.
Home care level 2 PP3 casual, first aid certificate.
```
**Expected**:
- Day work: 8h × [rate] × 1.25
- Sleepover: $60.02
- Vehicle: 40km × $0.96 = $38.40
- First aid: 8h × $0.52 = $4.16
- ✅ Sleepover valid (5h active before meets 4-hour rule)

---

## Edge Cases & Compliance Breaches

### Edge 1: Broken Shift Exactly at 12-Hour Limit
```
4 hours 8am-12pm, then 4 hours 8pm-midnight (exactly 16 hours span).
```
**Expected**:
- ❌ BREACH: 16 hours > 12-hour maximum
- Final period flagged as overtime 200%

### Edge 2: First Aid Weekly Cap Boundary
```
Worked exactly 38 hours with first aid certificate (part-time).
```
**Expected**:
- First aid: 38h × $0.52 = $19.76 (exactly at cap, not over)

### Edge 3: Travel Time on Public Holiday
```
2 hours travel between clients on Christmas Day (public holiday).
Permanent $30/hour.
```
**Expected**:
- Travel pay: 2h × $30 × 2.5 (public holiday) = $150
- Counts as ordinary hours (toward daily pool)

---

## Negative Tests (Should NOT Trigger Allowances)

### Negative 1: Regular Shift (No Broken Shift)
```
8 hours straight 9am-5pm with 30-minute meal break.
```
**Expected**:
- No broken shift allowance (only 1 work period)

### Negative 2: No Vehicle Use
```
8 hour shift, took public transport.
```
**Expected**:
- No vehicle allowance

### Negative 3: No First Aid Certificate
```
8 hours, no first aid qualification.
```
**Expected**:
- No first aid allowance

### Negative 4: Overtime with Advance Notice
```
Worked 2 hours overtime, but was told 3 days ago.
```
**Expected**:
- Overtime pay: Yes
- Meal allowance: No (notice given)

---

## Summary of Expected Outputs

For each test, the chatbot should return:

1. **Itemized Allowance Ledger**:
   ```
   | Allowance | Units | Rate | Amount |
   |-----------|-------|------|--------|
   | Broken shift (2 periods) | 1 | $20.82 | $20.82 |
   | Vehicle allowance | 45km | $0.96/km | $43.20 |
   | First aid | 8h | $0.52/h | $4.16 |
   ```

2. **Compliance Alerts**:
   - ✅ All periods meet minimum engagement
   - ✅ Broken shift span within 12-hour limit
   - ⚠️ First aid allowance capped at weekly maximum

3. **Total Breakdown**:
   ```
   Work: $450.00
   Allowances: $68.18
   Gross Pay: $518.18
   ```

4. **Clause Citations**:
   - Broken shift allowance: Clause 25.6
   - Vehicle allowance: Clause 20.7
   - First aid allowance: Clause 20.6
