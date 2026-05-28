"""Parse and chunk an NDIS Pricing Arrangements & Price Limits PDF.

The NDIS pricing document is published yearly as a long PDF. We:
1. Read text page-by-page with ``pypdf``.
2. Detect section headings ("1. Introduction", "2.4 Travel claims", ...) so a
   chunk can be cited by section.
3. Pack the per-section text into ~``chunk_chars`` blocks (the same packing
   strategy as the Fair Work scraper) so each chunk fits in the embedding
   model's context.

The output mirrors ``services.scraper.scrape_award`` — a list of dicts ready
for the management command to persist + embed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


# A leading line like "1.", "2.4", "10.3.2" followed by a title.
HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\s+([A-Z][^\n]{2,140})\s*$")
# Schedule / appendix headings: "Schedule A — Pricing", "Appendix 1".
APPENDIX_RE = re.compile(
    r"^\s*((?:Schedule|Appendix|Part|Section)\s+[A-Z0-9][A-Za-z0-9.\-]*)\s*[—–:\-]*\s*(.*)$"
)


class NDISPdfError(RuntimeError):
    pass


def _require_pypdf():
    if PdfReader is None:  # pragma: no cover
        raise NDISPdfError(
            "The 'pypdf' package is not installed. Run: pip install pypdf"
        )


def read_pages(pdf_path: str | Path) -> list[str]:
    """Read a PDF and return one text string per page (1-indexed by position)."""
    _require_pypdf()
    path = Path(pdf_path)
    if not path.exists():
        raise NDISPdfError(f"PDF not found: {path}")
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page should not fail ingest
            text = ""
        pages.append(_clean_page(text))
    return pages


def _clean_page(text: str) -> str:
    """Normalise whitespace / glue broken lines."""
    text = text.replace("\xa0", " ")
    # Drop standalone page numbers and trivial repeated headers/footers.
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.fullmatch(r"\d{1,4}", stripped):  # bare page number
            continue
        lines.append(stripped)
    cleaned = "\n".join(lines)
    # Collapse 3+ consecutive blank lines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _iter_sections(pages: list[str]):
    """Walk the pages yielding ``(section_no, title, page_no, body_lines)`` groups.

    A new section starts on every line that matches ``HEADING_RE`` or
    ``APPENDIX_RE``. Everything before the first heading is yielded as the
    document's preamble (``section_no=""``).
    """
    current = {"section_no": "", "title": "Preamble", "page_start": 1, "blocks": []}
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.split("\n"):
            heading = HEADING_RE.match(line) or APPENDIX_RE.match(line)
            if heading:
                if current["blocks"] or current["section_no"] or current["title"] != "Preamble":
                    yield current
                section_no = heading.group(1).strip()
                title = (heading.group(2) or "").strip() or section_no
                current = {
                    "section_no": section_no,
                    "title": title,
                    "page_start": page_no,
                    "blocks": [],
                }
                continue
            if line:
                current["blocks"].append((page_no, line))
    if current["blocks"]:
        yield current


def _pack_blocks(lines: list[tuple[int, str]], chunk_chars: int):
    """Pack ``(page_no, line)`` tuples into chunks no larger than ``chunk_chars``.

    Returns a list of ``(text, page_start, page_end)`` triples.
    """
    chunks: list[tuple[str, int, int]] = []
    buf_lines: list[str] = []
    buf_start = lines[0][0] if lines else 0
    buf_end = buf_start
    buf_len = 0

    def flush():
        nonlocal buf_lines, buf_len, buf_start, buf_end
        if buf_lines:
            chunks.append(("\n".join(buf_lines).strip(), buf_start, buf_end))
        buf_lines = []
        buf_len = 0

    for page_no, line in lines:
        line_len = len(line) + 1
        if buf_len + line_len > chunk_chars and buf_lines:
            flush()
            buf_start = page_no
        if not buf_lines:
            buf_start = page_no
        buf_lines.append(line)
        buf_end = page_no
        buf_len += line_len
    flush()
    return chunks


def chunk_pdf(pdf_path: str | Path, chunk_chars: int = 3600) -> list[dict]:
    """Parse a PDF and return embeddable chunk dicts.

    Each chunk: ``{section, page_start, page_end, chunk_index, content,
    token_estimate}``. ``chunk_index`` is unique across the document so it can
    serve as the stable Pinecone vector-id suffix.
    """
    pages = read_pages(pdf_path)
    if not pages:
        raise NDISPdfError(f"No text extracted from {pdf_path}")

    chunks: list[dict] = []
    global_index = 0
    for group in _iter_sections(pages):
        label = group["title"]
        if group["section_no"]:
            label = f"{group['section_no']} {group['title']}"
        header = label.strip()
        for body, page_start, page_end in _pack_blocks(group["blocks"], chunk_chars):
            if not body:
                continue
            content = f"[NDIS] {header}\n\n{body}".strip()
            chunks.append(
                {
                    "section": header[:300],
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_index": global_index,
                    "content": content,
                    "token_estimate": max(1, len(content) // 4),
                }
            )
            global_index += 1

    if not chunks:
        raise NDISPdfError(
            "Parsed 0 chunks - the PDF may be image-only (scanned) or unsupported."
        )
    return chunks


def make_vector_id(year: str, version: str, chunk_index: int) -> str:
    """Stable Pinecone vector id for an NDIS chunk."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{year}-{version}").strip("-") or "ndis"
    return f"ndis-{slug}-{chunk_index}"


def page_count(pdf_path: str | Path) -> int:
    _require_pypdf()
    return len(PdfReader(str(pdf_path)).pages)


__all__: Iterable[str] = (
    "NDISPdfError",
    "chunk_pdf",
    "read_pages",
    "page_count",
    "make_vector_id",
)
