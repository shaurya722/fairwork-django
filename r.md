# Payroll Report Test Cases

These test cases can be used to validate payroll calculation logic in a RAG system.

---

## Test 1: Weekday Evening Shift (Casual)

- **Start:** 05 Dec 2025 6:00 AM  
- **End:** 05 Dec 2025 2:00 PM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 8.0h | 1.25 | Normal rate casual | $345.80 |

### Total
**$345.80**

---

## Test 2: Saturday→Sunday Overnight (Casual)

- **Start:** 06 Dec 2025 9:30 PM  
- **End:** 07 Dec 2025 6:30 AM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 2.5h | 1.75 | Saturday rate | $151.29 |
| 6.0h | 2.25 | Sunday rate | $466.83 |
| 0.5h | 2.25 | Sunday rate | $38.90 |

### Total
**$657.02**

---

## Test 3: Sunday→Monday Overnight with Night Band (Casual)

- **Start:** 07 Dec 2025 9:30 PM  
- **End:** 08 Dec 2025 6:30 AM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 2.5h | 2.25 | Sunday rate | $194.51 |
| 6.0h | 1.40 | Night rate | $290.47 |
| 0.5h | 1.25 | Normal rate | $21.61 |

### Total
**$506.59**

---

## Test 4: Sleepover Shift with Evening + Normal (Casual)

- **Start:** 02 Dec 2025 5:00 PM  
- **End:** 03 Dec 2025 9:00 AM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 5.0h | 1.38 | Evening rate | $237.74 |
| 3.0h | 1.25 | Normal rate | $129.68 |

### Allowances
- Sleepover Allowance = 1 unit  
- KM Allowance = 2 units  

### Total
**$367.42 + allowances**

---

## Test 5: Public Holiday (Casual)

- **Start:** 26 Dec 2025 6:00 AM  
- **End:** 26 Dec 2025 2:00 PM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 8.0h | 2.75 | Public holiday rate | $760.76 |

### Total
**$760.76**

---

## Test 6: Overtime Shift (>10h Daily, Casual)

- **Start:** 30 Dec 2025 5:00 PM  
- **End:** 31 Dec 2025 9:00 AM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 3.0h | 1.25 | Normal rate | $129.68 |
| 3.5h | 1.38 | Evening rate | $166.42 |
| 1.5h | 1.75 | Overtime first 2h | $90.77 |

### Allowances
- Sleepover Allowance = 1 unit  
- KM Allowance = 18 units  

### Total
**$386.87 + allowances**

---

## Test 7: Evening Shift with Overtime (Casual, $35.67/hr)

- **Start:** 05 Dec 2025 2:00 PM  
- **End:** 05 Dec 2025 10:00 PM  
- **Rate:** $35.67/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 3.5h | 1.38 | Evening rate | $171.66 |
| 2.0h | 1.75 | Overtime first 2h | $124.85 |
| 2.5h | 2.25 | Overtime after 2h | $200.64 |

### Total
**$497.15**

---

## Test 8: Night Shift (Wed→Thu, Casual)

- **Start:** 04 Dec 2025 9:30 PM  
- **End:** 05 Dec 2025 6:30 AM  
- **Rate:** $35.67/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 0.5h | 1.25 | Normal rate | $22.29 |
| 2.5h | 1.40 | Night rate | $124.85 |
| 6.0h | 1.40 | Night rate | $299.63 |

### Total
**$446.77**

---

## Test 9: Sunday Full Shift (Casual)

- **Start:** 07 Dec 2025 2:00 PM  
- **End:** 07 Dec 2025 10:00 PM  
- **Rate:** $35.67/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 8.0h | 2.25 | Sunday rate | $642.06 |

### Total
**$642.06**

---

## Test 10: Saturday Shift (Casual)

- **Start:** 06 Dec 2025 6:00 AM  
- **End:** 06 Dec 2025 2:00 PM  
- **Rate:** $35.67/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 8.0h | 1.75 | Saturday rate | $499.38 |

### Total
**$499.38**

---

## Test 11: Public Holiday Evening Shift (Casual)

- **Start:** 25 Dec 2025 5:00 PM  
- **End:** 25 Dec 2025 10:30 PM  
- **Rate:** $35.67/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 5.5h | 2.75 | Public holiday rate | $539.51 |

### Total
**$539.51**

---

## Test 12: Sleepover with Sleep Disturbance (Casual)

- **Start:** 09 Dec 2025 5:00 PM  
- **End:** 10 Dec 2025 9:00 AM  
- **Rate:** $34.58/hr Casual  

### Breakdown
| Hours | Multiplier | Description | Amount |
|---|---|---|---|
| 5.0h | 1.38 | Evening rate | $237.74 |
| 3.0h | 1.25 | Normal rate | $129.68 |

### Allowances
- Sleepover Allowance = 1 unit  
- Sleep Disturbance = 8 units (0.72 hours)  

### Total
**$367.42 + allowances**

---

# Example Validation Queries

You can validate your RAG system using prompts like:

```text
"Casual $34.58/hr. Shift 06 Dec 2025 9:30pm to 07 Dec 2025 6:30am. Calculate pay."
```

### Expected Output
- Total: **$657.02**
- Includes:
  - Saturday rate calculations
  - Sunday rate calculations
  - Full breakdown by hours and multiplier

---