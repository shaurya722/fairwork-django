# Sleepover Detection Bug Fix

## Problem
The chatbot was **always adding sleepover allowance** even when users explicitly said:
- "without sleepover"
- "no sleepover"
- "not a sleepover"
- "regular shift"

## Root Cause
Two issues were found:

### 1. **LLM Extraction Prompt** (`services/llm.py`)
The prompt said to "default unknown booleans to false" but didn't give explicit rules for detecting sleepover negations.

### 2. **Hardcoded Override** (`services/rag.py` lines 472-482)
The code had a blanket rule:
```python
# OLD BUGGY CODE
if has_sleepover_keyword and not shift.get("is_sleepover"):
    shift["is_sleepover"] = True  # ← ALWAYS forced to True!
```

This meant if the user said **"Calculate my pay WITHOUT sleepover"**, the word "sleepover" triggered `is_sleepover=True` anyway.

---

## Fix Applied

### 1. Updated LLM Extraction Prompt
Added explicit sleepover detection rules in `services/llm.py`:

```python
- is_sleepover detection (CRITICAL — read the user's words carefully):
    • Set to TRUE only if the user explicitly mentions: "sleepover", "sleep over",
      "overnight", "sleep-over shift", "sleepover allowance".
    • Set to FALSE if the user says: "no sleepover", "without sleepover",
      "not a sleepover", "regular shift", "normal shift", "day shift".
    • Set to FALSE (default) when sleepover is NOT mentioned at all.
    • NEVER assume sleepover=true unless the user explicitly says it.
```

### 2. Fixed Negation Detection in RAG Pipeline
Updated `services/rag.py` to check for **negative phrases FIRST**:

```python
# NEW FIXED CODE
# Negative sleepover phrases (user explicitly says NO sleepover)
has_sleepover_negation = any(
    phrase in q_lower for phrase in (
        "no sleepover", "without sleepover", "not a sleepover",
        "no sleep over", "without sleep over", "not sleepover",
        "regular shift", "normal shift", "day shift"
    )
)

# Positive sleepover keywords (user wants sleepover)
has_sleepover_keyword = any(
    kw in q_lower for kw in ("sleepover", "sleep over", "slept over", "overnight")
)

for shift in payload.get("shifts") or []:
    if isinstance(shift, dict):
        # If user explicitly said NO sleepover, force it to false
        if has_sleepover_negation:
            shift["is_sleepover"] = False
        # If user mentioned sleepover (and didn't negate it) but LLM missed it, flip it
        elif has_sleepover_keyword and not shift.get("is_sleepover"):
            shift["is_sleepover"] = True
        # Default to false when not mentioned
        shift.setdefault("is_sleepover", False)
```

---

## Testing

### Before Fix ❌
```
User: "Calculate my pay for 8 hours WITHOUT sleepover, level 2 pay point 3, casual"
Result: Sleepover allowance added ($60.02) ← WRONG
```

### After Fix ✅
```
User: "Calculate my pay for 8 hours WITHOUT sleepover, level 2 pay point 3, casual"
Result: No sleepover allowance ← CORRECT

User: "Calculate my pay for 8 hours WITH sleepover, level 2 pay point 3, casual"
Result: Sleepover allowance added ($60.02) ← CORRECT
```

---

## Test Cases

| User Input | Expected `is_sleepover` | Reason |
|------------|------------------------|--------|
| "8 hours with sleepover" | `true` | Explicit mention |
| "overnight shift" | `true` | Synonym for sleepover |
| "8 hours without sleepover" | `false` | Explicit negation |
| "8 hours no sleepover" | `false` | Explicit negation |
| "regular 8 hour shift" | `false` | Implies not sleepover |
| "8 hours on Saturday" | `false` | Not mentioned = default false |

---

## Files Changed

1. **`services/llm.py`** (lines 174-180)
   - Added explicit sleepover detection rules to `EXTRACTION_SYSTEM_PROMPT`

2. **`services/rag.py`** (lines 472-501)
   - Added negation detection before positive keyword matching
   - Checks for "no sleepover", "without sleepover", etc. first
   - Only sets `is_sleepover=True` if positive keyword found AND no negation

---

## How It Works Now

```
User Question
     ↓
1. LLM extracts payload with is_sleepover based on new rules
     ↓
2. RAG pipeline double-checks:
     ↓
   ┌─────────────────────────┐
   │ Has negation phrase?    │
   │ ("no sleepover", etc.)  │
   └──────┬──────────────────┘
          │
    YES ──┴──→ is_sleepover = FALSE
          │
    NO ───┴──→ Check positive keywords
               ↓
          ┌─────────────────────────┐
          │ Has sleepover keyword?  │
          │ ("sleepover", etc.)     │
          └──────┬──────────────────┘
                 │
           YES ──┴──→ is_sleepover = TRUE
                 │
           NO ───┴──→ is_sleepover = FALSE (default)
```

---

## Restart Required?

**No restart needed** — the fix is in the Python code, which Django reloads automatically in development mode.

Just send a new chat request and the fix will apply immediately.
