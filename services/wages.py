"""Hourly wage rates for the Fair Work award's weekly-wage clauses.

The award (MA000100) publishes minimum wages "Per week" only — see clauses:

  * 15 — social & community services / crisis accommodation employees
  * 16 — family day care employees
  * 17 — home care employees

Dividing a weekly wage by the 38-hour standard working week gives the
equivalent ordinary hourly rate. This module augments the scraped, pipe-
separated wage tables with that hourly figure so the chatbot can answer
"what is the hourly rate for ..." questions directly, and exposes the rates
in a structured form for the ``/api/scrape/`` endpoint.

The text helpers here are pure Python; :func:`apply_hourly_rates` is the one
function that touches the database (it imports the model lazily).
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Standard full-time working week under the award (clause 25 — Ordinary hours).
WEEKLY_HOURS = Decimal("38")

# Clauses whose tables list minimum *weekly* wages.
WAGE_CLAUSE_NUMBERS = ("15", "16", "17")

# Label for the hourly-rate column added to each wage table.
HOURLY_HEADER = "Per hour $"


def hourly_from_weekly(weekly) -> Decimal:
    """Ordinary hourly rate = weekly wage / 38, rounded to whole cents."""
    weekly = weekly if isinstance(weekly, Decimal) else Decimal(str(weekly))
    return (weekly / WEEKLY_HOURS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_money(cell: str):
    """Return a positive ``Decimal`` if ``cell`` is a bare wage amount, else None."""
    token = cell.replace("$", "").replace(",", "").strip()
    if not token:
        return None
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _augment_line(line: str) -> str:
    """Add the hourly-rate cell to a single pipe-separated wage table line."""
    if "|" not in line:
        return line  # prose, headings and notes are left untouched.

    cells = [c.strip() for c in line.split("|")]
    if len(cells) != 2:
        # Only simple "label | weekly amount" rows gain a third column. Rows
        # that already carry an hourly cell (3 cells) or the multi-column
        # equal-remuneration table in clause 15 are skipped — this is what
        # keeps the transform idempotent.
        return line

    weekly = _parse_money(cells[1])
    if weekly is not None:
        return f"{line} | {hourly_from_weekly(weekly)}"

    # Header / sub-header row — give the new column a matching label so the
    # table still reads correctly.
    value = cells[1]
    if value == "$":
        return f"{line} | $"
    if "$" in value:
        return f"{line} | {HOURLY_HEADER}"
    return f"{line} | Per hour"


def inject_hourly_rates(content: str) -> str:
    """Return ``content`` with an hourly-rate column added to every wage row.

    Operates line by line on the pipe-separated tables produced by
    :mod:`services.scraper`. Safe to run repeatedly — rows that already carry
    an hourly cell are detected and left as-is.
    """
    return "\n".join(_augment_line(line) for line in content.split("\n"))


def extract_wage_rates(content: str, clause_no: str = "") -> list[dict]:
    """Parse wage rows out of a clause's content into structured dicts.

    Each dict is ``{clause_no, section, classification, weekly_rate,
    hourly_rate}``. ``section`` is the most recent sub-heading (e.g.
    "17.2 Home care employees—aged care") so a bare "Pay point 1" row keeps
    its context. Works on content both before and after
    :func:`inject_hourly_rates` has run.
    """
    rates: list[dict] = []
    section = ""
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if "|" not in line:
            # Track the latest sub-heading ("17.2 Home care employees—aged
            # care"). Skip the "[MA000100] Clause .." header and prose
            # sentences (which end in a full stop) so a wage row keeps a
            # genuine heading as its section.
            if not line.startswith("[") and not line.endswith(".") and len(line) <= 90:
                section = line
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) not in (2, 3):
            continue  # multi-column tables are not simple weekly-wage rows.
        weekly = _parse_money(cells[1])
        if weekly is None:
            continue
        rates.append(
            {
                "clause_no": clause_no,
                "section": section,
                "classification": cells[0],
                "weekly_rate": float(weekly),
                "hourly_rate": float(hourly_from_weekly(weekly)),
            }
        )
    return rates


def apply_hourly_rates(
    award_code: str = "MA000100", clause_numbers=WAGE_CLAUSE_NUMBERS
) -> int:
    """Augment an award's stored weekly-wage clauses with hourly rates.

    Rewrites the ``content`` of the wage clauses (15, 16, 17 by default) in
    SQLite, adding the "Per hour $" column. Any clause whose content changes
    is marked ``is_indexed=False`` so ``index_award`` re-embeds it. Returns the
    number of clause chunks changed. Idempotent — re-running changes nothing.
    """
    from awards.models import AwardClause  # lazy import: keeps helpers Django-free

    changed = []
    for clause in AwardClause.objects.filter(
        award_code=award_code, clause_no__in=list(clause_numbers)
    ):
        new_content = inject_hourly_rates(clause.content)
        if new_content != clause.content:
            clause.content = new_content
            clause.is_indexed = False  # content changed — must be re-embedded.
            clause.indexed_at = None
            changed.append(clause)
    if changed:
        AwardClause.objects.bulk_update(
            changed, ["content", "is_indexed", "indexed_at"]
        )
    return len(changed)


# ---------------------------------------------------------------------------
# Auto-lookup of hourly rates for the chat pay-calculator
# ---------------------------------------------------------------------------

# Clause numbers that contain wage tables for each SCHADS stream.
_STREAM_CLAUSE_MAP = {
    "SOCIAL_COMMUNITY_SERVICES": ("15",),
    "CRISIS_ACCOMMODATION": ("15",),
    "HOME_CARE": ("17",),
    "FAMILY_DAY_CARE": ("16",),
}


def _is_ero_section_row(cells: list[str]) -> bool:
    """True for a 6-cell ERO row whose first cell is a level heading."""
    if len(cells) != 6:
        return False
    first = cells[0].lower()
    return "employee level" in first or "employee level" in first


def _parse_all_wage_rows(content: str, clause_no: str = "") -> list[dict]:
    """Parse every wage row from a clause — base tables (3-col) AND ERO tables (6-col).

    Returns dicts with ``clause_no, section, classification, hourly_rate``.
    The hourly rate is the *current* rate from the ERO table when available,
    otherwise the base rate.
    """
    rates: list[dict] = []
    section = ""
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue

        # Plain-text headings (base tables).
        if "|" not in line:
            if not line.startswith("[") and not line.endswith(".") and len(line) <= 90:
                section = line
            continue

        cells = [c.strip() for c in line.split("|")]

        # 6-cell ERO table — detect section headings disguised as data rows.
        if len(cells) == 6:
            if _is_ero_section_row(cells):
                section = cells[0]
                continue
            if cells[0].lower().startswith("pay point") or cells[0].lower().startswith("level"):
                # Last cell is the current hourly wage.
                rate = _parse_money(cells[-1])
                if rate is not None:
                    rates.append(
                        {
                            "clause_no": clause_no,
                            "section": section,
                            "classification": cells[0],
                            "hourly_rate": float(rate),
                        }
                    )
            continue

        # 3-cell base table.
        if len(cells) == 3:
            if cells[0].lower().startswith("pay point") or cells[0].lower().startswith("level"):
                rate = _parse_money(cells[-1])
                if rate is not None:
                    rates.append(
                        {
                            "clause_no": clause_no,
                            "section": section,
                            "classification": cells[0],
                            "hourly_rate": float(rate),
                        }
                    )
            continue

        # 2-col table — also valid if the last cell is a money value.
        if len(cells) == 2:
            rate = _parse_money(cells[-1])
            if rate is not None and (cells[0].lower().startswith("pay point") or cells[0].lower().startswith("level")):
                rates.append(
                    {
                        "clause_no": clause_no,
                        "section": section,
                        "classification": cells[0],
                        "hourly_rate": float(rate),
                    }
                )

    return rates


def lookup_hourly_rate(stream: str, level: int | None, pay_point: int | None) -> float | None:
    """Look up the ordinary hourly rate for a stream + level + pay_point.

    Searches the stored wage clauses (15, 16, 17) in SQLite. Returns the
    *current* ERO rate when available, otherwise the base rate. Returns
    ``None`` when no matching row is found.
    """
    from awards.models import AwardClause  # lazy import

    stream = (stream or "").upper().strip()
    level = int(level) if level is not None else None
    pay_point = int(pay_point) if pay_point is not None else None

    clause_numbers = _STREAM_CLAUSE_MAP.get(stream, ())
    if not clause_numbers:
        return None

    # Collect every wage row from the relevant clauses.
    all_rows: list[dict] = []
    for clause in AwardClause.objects.filter(
        award_code="MA000100", clause_no__in=clause_numbers
    ):
        all_rows.extend(_parse_all_wage_rows(clause.content, clause.clause_no))

    # Build search terms.
    search_sections = []
    if stream == "CRISIS_ACCOMMODATION":
        search_sections.append(f"crisis accommodation employee level {level}")
        # Crisis level N also appears under social level (N+2) in base tables.
        if level is not None:
            search_sections.append(f"social and community services employee level {level + 2}")
    elif stream == "SOCIAL_COMMUNITY_SERVICES":
        search_sections.append(f"social and community services employee level {level}")
    elif stream == "HOME_CARE":
        search_sections.append(f"home care employee level {level}")
    elif stream == "FAMILY_DAY_CARE":
        search_sections.append(f"family day care employee level {level}")

    search_class = f"pay point {pay_point}" if pay_point is not None else ""

    # Collect all matching rows and prefer the highest rate.
    # ERO rates are always higher than base rates, so max() picks the
    # current rate when both tables contain the same classification.
    matches = []
    for row in all_rows:
        section_match = any(s.lower() in row["section"].lower() for s in search_sections)
        class_match = row["classification"].lower().startswith(search_class)
        if section_match and class_match:
            matches.append(row["hourly_rate"])

    if matches:
        return max(matches)

    # Fuzzy fallback: any row whose classification matches the pay point.
    fuzzy = [
        row["hourly_rate"]
        for row in all_rows
        if row["classification"].lower().startswith(search_class)
    ]
    if fuzzy:
        return max(fuzzy)

    return None
