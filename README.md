# Fair Work Award RAG Chatbot

A Django REST Framework chatbot that answers questions about the Australian
Fair Work award **[MA000100](https://awards.fairwork.gov.au/MA000100.html)**
(Social, Community, Home Care and Disability Services Industry Award).

It scrapes the award webpage, stores the clauses in **SQLite**, embeds them
into **Pinecone**, and answers questions with a local **Ollama** LLM using
**RAG** (Retrieval-Augmented Generation). Every prompt request and response
is logged to SQLite.

> **About "fine-tuning":** the chat is *grounded* on the Fair Work data via
> retrieval + a strict system prompt — it only answers from the scraped
> clauses and cites them. No model weights are trained; that is the practical
> way to "tune" a chatbot to a document with Ollama.

## Pipeline

```
scrape webpage  ->  SQLite (awards_awardclause)
                ->  Ollama embeddings  ->  Pinecone vectors

question  ->  embed  ->  Pinecone search  ->  top clauses
          ->  Ollama chat (grounded prompt)  ->  answer + citations
          ->  logged to SQLite (chatbot_chatlog)
```

Everything runs **synchronously inside the request** — no Celery / background
workers.

## Requirements

- Python 3.12, and the packages in `requirements.txt`
- [Ollama](https://ollama.com) running locally with two models:
  ```bash
  ollama pull qwen2.5:7b-instruct-q4_K_M   # chat model
  ollama pull nomic-embed-text             # embedding model
  ```
- A **Pinecone** account + API key (free tier works): https://app.pinecone.io

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure — then edit .env and set PINECONE_API_KEY
cp .env.example .env

python manage.py migrate
```

## Build the knowledge base

```bash
# 1. Scrape the award webpage into SQLite (91 clause chunks)
python manage.py scrape_award

# 2. Embed the chunks and upsert them into Pinecone
python manage.py index_award
```

Useful flags:

| Command | Flag | Effect |
|---|---|---|
| `scrape_award` | `--fresh` | Delete existing rows for the award first |
| `scrape_award` | `--url` / `--code` | Scrape a different award page |
| `index_award` | `--all` | Re-embed every clause, not just new ones |
| `index_award` | `--recreate` | Wipe the Pinecone namespace first |
| `add_hourly_rates` | `--code` | Add an hourly-rate column (weekly wage ÷ 38) to the weekly-wage clauses (15, 16, 17) |
| `import_holidays` | `--file` | Import public holidays from a CSV export (used by the pay calculator) |
| `import_calc_knowledge` | `--dir` | Import the SCHADS "Award Calculation" CSVs as chatbot knowledge-base docs |

`scrape_award` already runs `add_hourly_rates` at the end — the standalone
command is for retrofitting clauses that were scraped earlier.

`import_holidays` loads a public-holidays CSV (`id, date, holiday_name,
information, more_information, …`). It repairs mis-encoded text
(`Kingâ€™s Birthday` → `King's Birthday`), skips soft-deleted rows and test/
junk entries (rows with no government source URL), and is idempotent — rows
are matched on their original `id`:

```bash
python manage.py import_holidays --file public_holidays.csv
```

Once imported, the chat pay calculator applies these dates automatically: a
shift worked on a stored public holiday gets the 2.5×/2.75× loading without
the user listing the date.

`import_calc_knowledge` builds the calculation knowledge base from two
sources in the project directory: the four `Award Calculation - *.csv` files
(the engine Ticket, Rules, Penalty rates and Conditions & formula) and the
`Payroll Engine Guide.md` engine guide (the end-to-end shift pay-rate
process — segmentation, shift-type resolution, overtime, allowances and PAYG
tax). Both are stored under the award code `SCHADS-CALC`, separate from the
scraped award so a fresh re-scrape never wipes them:

```bash
python manage.py import_calc_knowledge
python manage.py index_award --code SCHADS-CALC   # embed them into Pinecone
```

After indexing, the chatbot retrieves these alongside the scraped award —
both old and new data form one knowledge base — so it can answer questions
about penalty rates, allowances, and the shift pay-rate calculation process.

## Run

```bash
python manage.py runserver
```

### API endpoints

| Method | URL | Purpose |
|---|---|---|
| `POST` | `/api/chat/` | Ask a question |
| `GET`  | `/api/chat/history/` | Recent chat logs (`?session_id=` filter) |
| `POST` | `/api/calculate/` | SCHADS pay calculation from raw time-logs |
| `POST` | `/api/scrape/` | Re-scrape the award (BeautifulSoup) + add hourly rates |
| `GET`  | `/api/health/` | Data + config status |
| —      | `/admin/` | Browse `AwardClause` and `ChatLog` |

### Ask a question

```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H 'Content-Type: application/json' \
  -d '{"message": "What are Sunday penalty rates?", "top_k": 5}'
```

Response:

```json
{
  "id": 12,
  "question": "What are Sunday penalty rates?",
  "answer": "Sunday work is paid at ... (Clause 28.x)",
  "sources": [
    {"clause_no": "28", "title": "Overtime and penalty rates",
     "score": 0.83, "excerpt": "...", "source_url": "..."}
  ],
  "success": true,
  "meta": {"retrieval_ms": 140, "llm_ms": 3200, "total_ms": 3400, "...": "..."}
}
```

## Refresh the award data

`POST /api/scrape/` re-scrapes the award page with **BeautifulSoup**, re-chunks
it into SQLite, and augments the minimum weekly-wage clauses (15, 16, 17) with
an **hourly-rate** column — the weekly wage divided by the 38-hour standard
week. Every field in the body is optional (`url`, `code`, `fresh`).

```bash
curl -X POST http://localhost:8000/api/scrape/ \
  -H 'Content-Type: application/json' -d '{"fresh": false}'
```

Response (abridged):

```json
{
  "success": true,
  "award_code": "MA000100",
  "weekly_hours": 38.0,
  "scraped_chunks": 91,
  "created": 0, "updated": 91,
  "wage_clauses_updated": 3,
  "wage_rates": [
    {"clause_no": "17", "section": "17.2 Home care employees—aged care",
     "classification": "Home care employee level 1—aged care",
     "weekly_rate": 1182.8, "hourly_rate": 31.13}
  ]
}
```

The hourly column also lands in the clause text, e.g.
`Home care employee level 1—aged care | 1182.80 | 31.13`, so the chatbot can
quote per-hour rates. After scraping, run `python manage.py index_award` to
re-embed the changed clauses. The same transform is available offline as
`python manage.py add_hourly_rates`.

## SCHADS pay calculation engine

`POST /api/calculate/` runs raw time-logs through the **11-step SCHADS Award
logic sequence** (minimum engagement, sleepover, weekend/public-holiday
loading, overtime, allowances, …) and returns itemised pay line items. It is
stateless — nothing is persisted. The engine lives in `services/schads.py`;
run it standalone to execute the ticket's $444.54 validation benchmark:

```bash
python services/schads.py
```

```bash
curl -X POST http://localhost:8000/api/calculate/ \
  -H 'Content-Type: application/json' \
  -d '{
    "employee": {"stream": "HOME_CARE", "classification_level": 2,
                 "pay_point": 1, "employment_type": "CASUAL",
                 "base_hourly_rate": 35.67},
    "shifts": [{"id": "night-1",
                "segments": [{"start": "2025-12-18T21:30:00",
                              "end": "2025-12-19T06:30:00"}]}],
    "tenant_config": {"meal_allowance": false, "uniform_allowance": false,
                      "laundry_allowance": false, "weekly_overtime": false}
  }'
```

Response (abridged):

```json
{
  "success": true,
  "currency": "AUD",
  "line_items": [
    {"type": "WORK", "description": "Evening work (weekday)", "hours": 2.5,
     "multiplier": 1.375, "rule": "Evening band rate", "amount": 122.62},
    {"type": "WORK", "description": "Night work (weekday)", "hours": 6.0,
     "multiplier": 1.4, "rule": "Night band rate", "amount": 299.63},
    {"type": "WORK", "description": "Ordinary work (weekday)", "hours": 0.5,
     "multiplier": 1.25, "rule": "Ordinary band rate", "amount": 22.29}
  ],
  "totals": {"work": 444.54, "allowances": 0.0, "gross": 444.54},
  "warnings": []
}
```

Notes: the base hourly rate is supplied per request; the base rate, allowance
toggles (meal/uniform/laundry) and weekly-overtime mode are tenant-driven via
`tenant_config`. Each worked minute is billed at the single highest applicable
multiplier — rates never compound. See the docstring in `services/schads.py`
for the full input schema and interpretation notes.

### Calculations inside the chatbot

`POST /api/chat/` also understands pay questions in plain English. When a
question looks like a calculation (e.g. *"How much do I earn for a casual
night shift on $35.67/hr from 9:30pm to 6:30am?"*), the pipeline:

1. asks the LLM to **extract** a structured payload from the question,
2. runs the **verified `schads` engine** on it,
3. asks the LLM to **explain** the engine's result in plain English.

The chat response carries the structured figures under a `calculation` key
alongside the natural-language `answer`. If required details are missing the
bot asks for them; if the LLM is unavailable the engine's numbers are still
returned via a deterministic text breakdown. Every other question falls
through to the normal RAG award-clause lookup.

### Conversation memory

Send a `session_id` with each `POST /api/chat/` call and the bot **remembers
the conversation** — the user does not have to repeat earlier context:

```
Turn 1:  "I'm a casual on $35.67/hr"
Turn 2:  "How much for a 9-hour night shift?"   ← rate + casual carried over
Turn 3:  "What about a 10-hour shift instead?"  ← everything carried over
```

How it works: every turn is already persisted to `ChatLog` with its
`session_id`. On each request the last `_HISTORY_TURNS` (6) successful turns
for that session are loaded and replayed to the LLM as prior chat messages —
for both the RAG answer and the SCHADS extraction step. `GET
/api/chat/history/?session_id=…` returns a session's turns so a frontend can
restore the conversation after a reload. The bundled `chatbot.html` does this:
it keeps a stable `session_id` in `localStorage`, replays the conversation on
load, and has a **New chat** button to start a fresh session.

## Data stored in SQLite

- **`awards_awardclause`** — one row per scraped clause chunk (part, clause
  number, title, text, token estimate, Pinecone `vector_id`, indexed flag).
- **`chatbot_chatlog`** — one row per chat call: the question, the answer,
  the source citations, the retrieved context, model names and timing — the
  full "prompt request & response data".

## Project layout

```
config/        Django project (settings, urls)
awards/        AwardClause model + scrape_award / index_award commands
chatbot/       ChatLog model + chat & calculate API (DRF views, serializers)
services/      scraper · embeddings · vectorstore (Pinecone) · llm · rag · schads
```

## Configuration

All settings come from `.env` (see `.env.example`). Key variables:
`PINECONE_API_KEY`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `RAG_TOP_K`.

> If you switch the embedding model, its vector dimension changes — use a new
> `PINECONE_INDEX_NAME` or run `index_award --recreate`.
