# Unified Chatbot Architecture

## Overview

The chatbot now has **two API endpoints** with different scopes:

### 1. `/api/chat/` — **Unified Chatbot** (Everything)
**Handles all question types automatically:**
- ✅ Fair Work award questions (clause citations)
- ✅ NDIS pricing questions (support categories, price limits)
- ✅ SCHADS pay calculations (shifts, penalties, allowances, public holidays)
- ✅ Wage lookups (classification levels, pay points)
- ✅ Overtime, casual loading, sleepover allowances

**How it works:**
1. Question comes in via `POST /api/chat/`
2. `llm.classify_question()` detects if it's NDIS-related (keyword-based, fast)
3. Routes to:
   - `services.ndis_rag` → NDIS pricing documents (if NDIS keywords detected)
   - `services.rag` → Fair Work award + SCHADS calculations (default)
4. Returns unified response with `meta.route` showing which path was used

**Example requests:**

```bash
# Fair Work question → routes to award RAG
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What are Sunday penalty rates for casual employees?"}'

# NDIS question → routes to NDIS RAG
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the NDIS price limit for daily activities?"}'

# SCHADS calculation → routes to award RAG + calculation engine
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Calculate my pay for 8 hours on Sunday, homecare level 2 pay point 3, casual"}'
```

**Response shape:**
```json
{
  "id": 123,
  "question": "What are Sunday penalty rates?",
  "answer": "...",
  "sources": [...],
  "calculation": {...},           // only present for pay calculations
  "ndis_document": {...},         // only present for NDIS questions
  "success": true,
  "error": "",
  "meta": {
    "chat_model": "ollama",
    "embed_model": "nomic-embed-text",
    "top_k": 5,
    "matches_found": 3,
    "retrieval_ms": 45,
    "llm_ms": 890,
    "total_ms": 935,
    "route": "award"              // "award" or "ndis"
  }
}
```

---

### 2. `/api/ndis-chat/` — **NDIS-Only Endpoint**
**Scoped exclusively to NDIS pricing documents:**
- ✅ NDIS support categories, price limits, item numbers
- ✅ Year-specific queries (can override with `"year": "2024-25"`)
- ❌ Never runs SCHADS calculations
- ❌ Never searches Fair Work award clauses

**Use this when:**
- You want to guarantee NDIS-only answers
- You need to query a specific year's pricing document
- You're building an NDIS-specific UI

**Example:**
```bash
curl -X POST http://localhost:8000/api/ndis-chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What changed in transport pricing?", "year": "2024-25"}'
```

---

## Classification Logic

The classifier in `services/llm.py` uses **keyword matching** (fast, no LLM call):

**NDIS keywords** (triggers NDIS route):
- `ndis`, `ndia`, `national disability insurance`
- `support category`, `support item`, `price limit`
- `core support`, `capacity building`, `capital support`
- `plan management`, `support coordination`
- `daily activities`, `community participation`
- `transport`, `consumables`, `assistive technology`
- `home modification`, `sil`, `supported independent living`

**Fair Work keywords** (overrides NDIS, forces award route):
- `schads`, `fair work`, `award`, `clause`
- `penalty rate`, `overtime`, `casual loading`
- `shift`, `hourly rate`, `pay point`, `classification level`
- `sleepover`, `home care`, `social community services`
- `public holiday`, `weekend`, `allowance`

**Default**: If no keywords match → routes to Fair Work (most common use case)

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    POST /api/chat/                          │
│                  (Unified Chatbot)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ llm.classify_question │
              │   (keyword-based)     │
              └──────────┬────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
    ┌──────────────┐          ┌──────────────┐
    │  is_ndis=True│          │ is_ndis=False│
    └──────┬───────┘          └──────┬───────┘
           │                         │
           ▼                         ▼
  ┌────────────────┐        ┌────────────────┐
  │ ndis_rag       │        │ rag            │
  │ (NDIS docs)    │        │ (Award + Calc) │
  └────────┬───────┘        └────────┬───────┘
           │                         │
           │                         ▼
           │              ┌──────────────────┐
           │              │ Calculation?     │
           │              │ (extract_calc)   │
           │              └────────┬─────────┘
           │                       │
           │              ┌────────┴────────┐
           │              │                 │
           │              ▼                 ▼
           │         ┌────────┐      ┌──────────┐
           │         │ Engine │      │ Award    │
           │         │ Result │      │ Clauses  │
           │         └────┬───┘      └─────┬────┘
           │              │                │
           └──────────────┴────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │  Unified Response│
                │  + ChatLog row   │
                └──────────────────┘
```

---

## Storage

All conversations are stored in `ChatLog` with:
- **NDIS questions**: prefixed with `[NDIS]` in the `question` field
- **Award questions**: stored as-is
- Same session can contain both NDIS and award questions
- Frontend session sidebar shows all questions together

---

## Frontend Integration

**No changes needed** if you're already using `/api/chat/`:
- The endpoint signature is identical
- Response shape is backward-compatible (added optional fields)
- The `meta.route` field tells you which pipeline was used

**Optional enhancement**:
- Display an NDIS badge when `meta.route === "ndis"`
- Show calculation breakdown when `calculation` is present
- Show NDIS document year when `ndis_document` is present

---

## Testing

```bash
# Test Fair Work route
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the casual loading for SCHADS?"}'

# Test NDIS route
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the NDIS price limits for transport?"}'

# Test calculation route
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Calculate pay for 6 hours on Saturday, level 3 pay point 2, permanent"}'

# Test NDIS-only endpoint (explicit)
curl -X POST http://localhost:8000/api/ndis-chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the hourly rate for support coordination?"}'
```

---

## Summary

| Feature | `/api/chat/` | `/api/ndis-chat/` |
|---------|-------------|-------------------|
| Fair Work awards | ✅ | ❌ |
| NDIS pricing | ✅ | ✅ |
| SCHADS calculations | ✅ | ❌ |
| Auto-routing | ✅ | N/A (always NDIS) |
| Year override | ❌ | ✅ |
| Use case | **General chatbot** | **NDIS-specific UI** |
