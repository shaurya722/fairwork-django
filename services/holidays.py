"""Public holidays for SCHADS pay calculations.

Holidays are imported from a CSV export (``manage.py import_holidays``) and
stored in the :class:`awards.models.PublicHoliday` table. The chat pay-
calculation path applies them automatically so a shift worked on a public
holiday gets the right penalty loading without the user listing the dates.

The CSV export is doubly-encoded in places — UTF-8 bytes read back as
Windows-1252 — so names like "King's Birthday" arrive as "Kingâ€™s Birthday".
:func:`fix_mojibake` repairs that. Rows without a real government source URL
are test / junk entries and are skipped on import.

The DB-touching helpers import the model lazily, keeping this module light.
"""

import csv
from datetime import date as date_cls


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text that was mis-decoded as Windows-1252.

    "Kingâ€™s Birthday" -> "King's Birthday". Text that is already correct is
    returned unchanged — the round-trip fails cleanly and falls through.
    """
    if not text:
        return text or ""
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _is_blank(value) -> bool:
    """True for CSV cells that mean "no value" — empty or the literal NULL."""
    return value is None or str(value).strip() in ("", "NULL")


def holiday_dates(tenant_id: str = "") -> list[str]:
    """Distinct public-holiday dates as ISO ``yyyy-mm-dd`` strings.

    Passed straight into the SCHADS engine's ``public_holidays`` input.
    """
    from awards.models import PublicHoliday  # lazy import — keep module light

    queryset = PublicHoliday.objects.all()
    if tenant_id:
        queryset = queryset.filter(tenant_id=tenant_id)
    dates = queryset.values_list("date", flat=True).distinct()
    return [d.isoformat() for d in dates]


def import_rows(rows) -> dict:
    """Upsert public-holiday rows (dicts from the CSV export) into the DB.

    Each row needs ``id``, ``date``, ``holiday_name`` and ``more_information``.
    Rows that are soft-deleted, undated, or carry no real source URL (test /
    junk entries) are skipped. Returns a stats dict. Idempotent on re-run —
    rows are matched on their original ``id``.
    """
    from awards.models import PublicHoliday  # lazy import

    stats = {
        "created": 0,
        "updated": 0,
        "skipped_junk": 0,
        "skipped_deleted": 0,
        "errors": 0,
    }

    for row in rows:
        if not _is_blank(row.get("deleted_at")):
            stats["skipped_deleted"] += 1
            continue

        url = (row.get("more_information") or "").strip()
        # Real holidays cite a government source URL; test/junk rows do not.
        if _is_blank(url) or not url.lower().startswith("http"):
            stats["skipped_junk"] += 1
            continue

        try:
            day = date_cls.fromisoformat((row.get("date") or "").strip()[:10])
        except ValueError:
            stats["errors"] += 1
            continue

        source_id = (row.get("id") or "").strip() or None
        _, created = PublicHoliday.objects.update_or_create(
            source_id=source_id,
            defaults={
                "date": day,
                "name": fix_mojibake((row.get("holiday_name") or "").strip()),
                "information": fix_mojibake((row.get("information") or "").strip()),
                "source_url": url,
                "tenant_id": (row.get("tenant_id") or "").strip(),
            },
        )
        stats["created" if created else "updated"] += 1

    return stats


def import_csv(path: str) -> dict:
    """Import public holidays from a CSV file. Returns the import stats dict."""
    with open(path, newline="", encoding="utf-8") as handle:
        return import_rows(csv.DictReader(handle))
