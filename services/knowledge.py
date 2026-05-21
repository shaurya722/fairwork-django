"""SCHADS calculation reference CSVs as chatbot knowledge-base documents.

The four "Award Calculation" spreadsheets — the engine Ticket, the Rules, the
Penalty rates and the Conditions & formula — describe how SCHADS pay is
calculated. This module flattens each CSV into a readable text document and
chunks it so it can be stored as :class:`awards.models.AwardClause` rows and
embedded alongside the scraped award. That lets the chatbot retrieve and
ground answers on the calculation rules, penalty rates and allowances.

The DB write goes through :func:`awards.ingest.store_clauses`; embedding is
done by ``manage.py index_award --code SCHADS-CALC``.
"""

import csv
import os

# Award code for the calculation knowledge base — kept separate from the
# scraped award (MA000100) so a fresh re-scrape does not wipe these docs.
KNOWLEDGE_AWARD_CODE = "SCHADS-CALC"
KNOWLEDGE_PART = "SCHADS Calculation Knowledge Base"

# The SCHADS engine Ticket is the authoritative source. Where the Penalty and
# Rules sheets give a different figure, the Ticket value is substituted so the
# whole knowledge base stays consistent with the calculation engine
# (services/schads.py).
_RECONCILE = (
    ("16.81", "15.54"),                # meal allowance — Ticket Step 5
    ("$0.92 per km", "$0.99 per km"),   # travel / KM allowance — Ticket Step 11
)

# Prepended to every knowledge chunk so any retrieval makes the precedence
# explicit to the LLM.
_AUTHORITY_NOTE = (
    "Authoritative source — SCHADS engine Ticket. The engine Ticket governs "
    "wherever the Penalty or Rules sheets differ: meal allowance is $15.54, "
    "travel is $0.99 per km, and sleepover disturbance is paid at the overtime "
    "rate. The figures in this document have been reconciled to the Ticket."
)


# ---------------------------------------------------------------------------
# Clear existing knowledge (used by --fresh)
# ---------------------------------------------------------------------------

def clear_knowledge(award_code: str = KNOWLEDGE_AWARD_CODE) -> int:
    """Delete all AwardClause rows for the given knowledge award code.

    Returns the number of rows deleted.
    """
    from awards.models import AwardClause  # lazy import — keeps module Django-free at top level

    qs = AwardClause.objects.filter(award_code=award_code)
    count = qs.count()
    qs.delete()
    return count

# (filename, clause_no, title, one-line description)
KNOWLEDGE_FILES = (
    (
        "Award Calculation - Ticket (1).csv",
        "Calc-Ticket",
        "SCHADS Award Calculation Engine — Specification",
        "The 11-step SCHADS pay-calculation logic, input schema, multiplier "
        "matrix, partitioning rules and the $444.54 validation benchmark.",
    ),
    (
        "Award Calculation - Rules.csv",
        "Calc-Rules",
        "SCHADS Calculation Rules — Shift Definitions & Allowances",
        "Shift-type definitions and rates, allowance amounts, the SCHADS rule "
        "list and worked shift examples.",
    ),
    (
        "Award Calculation - Copy of  Penalty.csv",
        "Calc-Penalty",
        "SCHADS Penalty Rates & Allowances",
        "Penalty multipliers by shift type for permanent/full-time and casual "
        "employees, plus the full list of allowance amounts.",
    ),
    (
        "Award Calculation - Condition & formula.csv",
        "Calc-Conditions",
        "SCHADS Calculation Conditions & Pay Formula",
        "The condition checklist, the unified pay formula and worked "
        "calculation examples.",
    ),
)

# Markdown / plain-text knowledge documents — chunked by section heading
# rather than CSV-flattened. (filename, clause_no, title)
KNOWLEDGE_DOCS = (
    (
        "Payroll Engine Guide.md",
        "Calc-Engine-Guide",
        "SCHADS Payroll Engine — Complete Calculation Guide",
    ),
)


def csv_to_text(path: str) -> str:
    """Flatten a (messy, sparse) CSV into readable text.

    Empty rows are dropped; within a row, empty cells are dropped and the rest
    are formatted as a Markdown table row when there are 3+ cells, or plain
    joined text for prose cells. This keeps every value while staying readable
    enough for embedding and for the LLM to ground answers on.
    """
    lines = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            cells = [c.strip() for c in row]
            cells = [c for c in cells if c]
            if not cells:
                continue
            # Format rows with 3+ cells as Markdown table rows for better
            # structure during embedding / grounding.
            if len(cells) >= 3:
                lines.append(" | ".join(cells))
            else:
                lines.append("  ".join(cells))
    return "\n".join(lines)


def _chunk_text(text: str, limit: int, overlap: int = 200) -> list[str]:
    """Pack text lines into chunks no larger than ``limit`` characters.

    Adjacent chunks share ``overlap`` characters so a retrieval at a
    boundary does not lose context.
    """
    chunks, buf = [], ""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if len(line) > limit:
            # An oversized single line — flush, then hard-wrap it.
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(line[i:i + limit] for i in range(0, len(line), limit))
            continue
        if buf and len(buf) + len(line) + 1 > limit:
            chunks.append(buf)
            # Carry the last few lines forward as overlap context.
            overlap_lines = []
            overlap_len = 0
            for prev_line in reversed(buf.split("\n")):
                if overlap_len + len(prev_line) + 1 > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_len += len(prev_line) + 1
            buf = "\n".join(overlap_lines)
            if buf:
                buf = f"{buf}\n{line}"
            else:
                buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        chunks.append(buf)
    return chunks


def load_from_fixture(path: str = "awards/fixtures/schads_calc_knowledge.json") -> tuple[list[dict], list[str]]:
    """Load SCHADS-CALC knowledge chunks from a Django JSON fixture.

    Returns ``(chunks, missing)`` in the same shape as
    :func:`build_knowledge_chunks` so the rest of the pipeline is unchanged.
    """
    import json

    chunks: list[dict] = []
    missing: list[str] = []
    fixture_path = os.path.join(os.getcwd(), path)
    if not os.path.isfile(fixture_path):
        missing.append(path)
        return chunks, missing

    with open(fixture_path, encoding="utf-8") as fh:
        data = json.load(fh)

    for entry in data:
        fields = entry.get("fields", {})
        chunks.append(
            {
                "award_code": fields.get("award_code", KNOWLEDGE_AWARD_CODE),
                "part": fields.get("part", KNOWLEDGE_PART),
                "clause_no": fields.get("clause_no", ""),
                "title": fields.get("title", ""),
                "chunk_index": fields.get("chunk_index", 0),
                "content": fields.get("content", ""),
                "token_estimate": fields.get("token_estimate", 0),
                "source_url": fields.get("source_url", ""),
            }
        )
    return chunks, missing


def _split_markdown(text: str) -> list[str]:
    """Split a markdown document into sections at level-2 (## ) headings.

    Fenced code blocks are tracked so a ``## `` inside a code sample never
    triggers a split.
    """
    sections: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## ") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def _pack_sections(sections: list[str], limit: int) -> list[str]:
    """Pack whole markdown sections into chunks no larger than ``limit``.

    A section is kept intact wherever it fits; an oversized section is split
    further with :func:`_chunk_text`.
    """
    chunks: list[str] = []
    buf = ""
    for section in sections:
        if len(section) > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_chunk_text(section, limit))
            continue
        if buf and len(buf) + len(section) + 2 > limit:
            chunks.append(buf)
            buf = section
        else:
            buf = f"{buf}\n\n{section}" if buf else section
    if buf:
        chunks.append(buf)
    return chunks


def _emit_chunks(pieces: list[str], clause_no: str, title: str) -> list[dict]:
    """Wrap text pieces as knowledge-chunk dicts, each carrying the title and
    the authoritative-source note."""
    out: list[dict] = []
    for idx, piece in enumerate(pieces):
        heading = title if idx == 0 else f"{title} (continued)"
        content = f"{heading}\n\n{_AUTHORITY_NOTE}\n\n{piece}"
        out.append(
            {
                "award_code": KNOWLEDGE_AWARD_CODE,
                "part": KNOWLEDGE_PART,
                "clause_no": clause_no,
                "title": title,
                "chunk_index": idx,
                "content": content,
                "token_estimate": max(1, len(content) // 4),
                "source_url": "",
            }
        )
    return out


def build_knowledge_chunks(base_dir: str, chunk_chars: int = 3600):
    """Build knowledge-chunk dicts from the Award Calculation CSVs and the
    markdown engine guides.

    Returns ``(chunks, missing)`` — ``chunks`` are ready for
    :func:`awards.ingest.store_clauses`; ``missing`` lists any expected source
    files that were not found in ``base_dir``.
    """
    chunks: list[dict] = []
    missing: list[str] = []

    # 1. Spreadsheet references — flattened to text, then character-chunked.
    for filename, clause_no, title, description in KNOWLEDGE_FILES:
        path = os.path.join(base_dir, filename)
        if not os.path.isfile(path):
            missing.append(filename)
            continue
        body = csv_to_text(path)
        for old, new in _RECONCILE:  # reconcile conflicts to the Ticket.
            body = body.replace(old, new)
        document = f"{description}\n\n{body}"
        chunks.extend(
            _emit_chunks(_chunk_text(document, chunk_chars), clause_no, title)
        )

    # 2. Markdown guides — split on section headings, packed into chunks so a
    #    section stays whole wherever it fits.
    for filename, clause_no, title in KNOWLEDGE_DOCS:
        path = os.path.join(base_dir, filename)
        if not os.path.isfile(path):
            missing.append(filename)
            continue
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for old, new in _RECONCILE:
            body = body.replace(old, new)
        pieces = _pack_sections(_split_markdown(body), chunk_chars)
        chunks.extend(_emit_chunks(pieces, clause_no, title))

    return chunks, missing
