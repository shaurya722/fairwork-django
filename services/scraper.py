"""Scrape and chunk a Fair Work award HTML page.

The Fair Work award pages (e.g. MA000100.html) are a single long HTML
document. Content is laid out as ``<p>`` elements carrying structural CSS
classes:

* ``Partheading`` -> a Part heading ("Part 4— Minimum Wages...")
* ``Level1``      -> a numbered clause heading ("15. Minimum weekly wages...")
* ``Subdocument`` -> Schedule headings ("Schedule B —Classification...")
* ``Level2``/``SubLevelN``/``BlockN``/``Bullet1``/... -> clause body text
* ``TOC1``/``TOC2``/``History``/``Header``/``Footer`` -> noise (skipped)

Wage/allowance figures live in ``<table>`` elements which are rendered to
pipe-separated text so they stay searchable.
"""

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; FairWorkRAGBot/1.0)"

# Paragraph classes that are layout noise rather than award content.
SKIP_CLASSES = {"TOC1", "TOC2", "History", "Header", "Footer"}

# "15. Minimum weekly wages..."  /  "7A. Workplace delegates' rights"
CLAUSE_RE = re.compile(r"^\s*(\d+[A-Z]?)\.\s*(.+)$")
# "Schedule B —Classification Definitions..."
SCHEDULE_RE = re.compile(r"^\s*Schedule\s+([A-Z]+)\b\s*[—–-]*\s*(.*)$", re.IGNORECASE)


class ScrapeError(RuntimeError):
    pass


def fetch_html(url: str, timeout: int = 60) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network
        raise ScrapeError(f"Could not fetch {url}: {exc}") from exc
    # Fair Work award pages are UTF-8 but do not always declare a charset in
    # the HTTP headers, which makes requests fall back to ISO-8859-1 and
    # mangle em-dashes ("—" -> "â€”"). Decode as the page actually is.
    if resp.encoding is None or resp.encoding.lower() in ("iso-8859-1", "latin-1"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _clean(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _render_table(table) -> str:
    """Flatten an HTML table to one pipe-separated line per row."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def parse_award(html: str):
    """Parse award HTML into ordered clause groups.

    Returns a list of dicts: ``{part, clause_no, title, blocks: [str, ...]}``.
    """
    soup = BeautifulSoup(html, "lxml")
    groups = []
    current = None
    part = ""
    started = False

    def new_group(clause_no: str, title: str):
        nonlocal current
        current = {"part": part, "clause_no": clause_no, "title": title, "blocks": []}
        groups.append(current)

    for el in soup.find_all(["p", "table"]):
        # <p> nested inside a <table> is handled when we reach the <table>.
        if el.name == "p" and el.find_parent("table") is not None:
            continue

        if el.name == "table":
            if started and current is not None:
                rendered = _render_table(el)
                if rendered:
                    current["blocks"].append(rendered)
            continue

        classes = el.get("class") or []
        cls = classes[0] if classes else ""
        text = _clean(el.get_text(" ", strip=True))
        if not text:
            continue

        if cls == "Partheading":
            started = True
            part = text
            continue

        # Skip page chrome before the award body begins.
        if not started:
            continue

        if cls == "Level1":
            match = CLAUSE_RE.match(text)
            if match:
                new_group(match.group(1), _clean(match.group(2)))
            else:
                new_group("", text)
            continue

        if cls == "Subdocument":
            match = SCHEDULE_RE.match(text)
            if match:
                new_group(f"Schedule {match.group(1)}", _clean(match.group(2)) or text)
                continue
            # Otherwise treat as ordinary body text (handled below).

        if cls in SKIP_CLASSES:
            continue

        if current is not None:
            current["blocks"].append(text)

    return groups


def _hard_wrap(line: str, limit: int):
    return [line[i:i + limit] for i in range(0, len(line), limit)]


def _split_long_block(block: str, limit: int):
    """Split a single oversized block (usually a big table) on line breaks."""
    pieces, buf = [], ""
    for line in block.split("\n"):
        if len(line) > limit:
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.extend(_hard_wrap(line, limit))
            continue
        if buf and len(buf) + len(line) + 1 > limit:
            pieces.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        pieces.append(buf)
    return pieces


def _pack(blocks, limit: int):
    """Pack body blocks into chunks no larger than ``limit`` characters."""
    chunks, buf = [], ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_long_block(block, limit))
            continue
        if buf and len(buf) + len(block) + 2 > limit:
            chunks.append(buf)
            buf = block
        else:
            buf = f"{buf}\n\n{block}" if buf else block
    if buf:
        chunks.append(buf)
    return chunks


def chunk_groups(groups, award_code: str, source_url: str, chunk_chars: int):
    """Turn clause groups into embeddable chunk dicts."""
    chunks = []
    for group in groups:
        bodies = _pack(group["blocks"], chunk_chars)
        if not bodies:
            continue
        header = f"[{award_code}]"
        if group["clause_no"]:
            header += f" Clause {group['clause_no']}:"
        header = f"{header} {group['title']}".strip()
        for idx, body in enumerate(bodies):
            content = f"{header}\n\n{body}".strip()
            chunks.append(
                {
                    "award_code": award_code,
                    "part": group["part"],
                    "clause_no": group["clause_no"],
                    "title": group["title"],
                    "chunk_index": idx,
                    "content": content,
                    "token_estimate": max(1, len(content) // 4),
                    "source_url": source_url,
                }
            )
    return chunks


def scrape_award(url: str, award_code: str, chunk_chars: int = 3600):
    """Fetch, parse and chunk an award. Returns a list of chunk dicts."""
    html = fetch_html(url)
    groups = parse_award(html)
    chunks = chunk_groups(groups, award_code, url, chunk_chars)
    if not chunks:
        raise ScrapeError(
            "Parsed 0 chunks - the award page layout may have changed."
        )
    return chunks
