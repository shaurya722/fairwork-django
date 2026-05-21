"""Persist scraped award clause chunks into SQLite.

Shared by the ``scrape_award`` management command and the ``/api/scrape/``
endpoint so both store clauses exactly the same way.
"""

import re

from .models import AwardClause


def make_vector_id(award_code: str, clause_no: str, chunk_index: int) -> str:
    """Stable Pinecone vector id for a clause chunk."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clause_no).strip("-") or "x"
    return f"{award_code}-{slug}-{chunk_index}"


def store_clauses(chunks, award_code: str, fresh: bool = False):
    """Upsert clause chunks into SQLite.

    With ``fresh=True`` the award's existing rows are deleted first. Returns a
    ``(created, updated, removed)`` tuple. Stored chunks are marked
    ``is_indexed=False`` so ``index_award`` re-embeds new/changed content.
    """
    removed = 0
    if fresh:
        removed, _ = AwardClause.objects.filter(award_code=award_code).delete()

    created = updated = 0
    for chunk in chunks:
        _, was_created = AwardClause.objects.update_or_create(
            award_code=chunk["award_code"],
            clause_no=chunk["clause_no"],
            chunk_index=chunk["chunk_index"],
            defaults={
                "part": chunk["part"],
                "title": chunk["title"],
                "content": chunk["content"],
                "token_estimate": chunk["token_estimate"],
                "source_url": chunk["source_url"],
                "vector_id": make_vector_id(
                    chunk["award_code"], chunk["clause_no"], chunk["chunk_index"]
                ),
                # New/changed content must be re-embedded.
                "is_indexed": False,
                "indexed_at": None,
            },
        )
        created += int(was_created)
        updated += int(not was_created)
    return created, updated, removed
