from django.db import models


class AwardClause(models.Model):
    """A single retrievable chunk of the scraped Fair Work award.

    Stored in SQLite. Each row also gets an embedding pushed to Pinecone;
    `vector_id` links the SQLite row to its Pinecone vector.
    """

    award_code = models.CharField(max_length=20, default="MA000100", db_index=True)
    part = models.CharField(max_length=300, blank=True)
    clause_no = models.CharField(max_length=30, blank=True, db_index=True)
    title = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    chunk_index = models.PositiveIntegerField(default=0)
    token_estimate = models.PositiveIntegerField(default=0)
    source_url = models.URLField(max_length=500, blank=True)

    # Pinecone sync state.
    vector_id = models.CharField(max_length=120, blank=True, db_index=True)
    is_indexed = models.BooleanField(default=False)
    indexed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["clause_no", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["award_code", "clause_no", "chunk_index"],
                name="unique_clause_chunk",
            )
        ]

    def __str__(self):
        return f"{self.award_code} cl.{self.clause_no} [{self.chunk_index}] {self.title}"[:90]

    @property
    def citation(self) -> str:
        label = f"Clause {self.clause_no}" if self.clause_no else "Award"
        return f"{label} — {self.title}" if self.title else label


class PublicHoliday(models.Model):
    """A public holiday used by the SCHADS pay calculator.

    Imported from a CSV export via ``manage.py import_holidays``. A shift
    worked on one of these dates attracts public-holiday penalty loading
    (2.5x / 2.75x) — the chat pay-calculation path applies them automatically.
    """

    date = models.DateField(db_index=True)
    name = models.CharField(max_length=200)
    information = models.TextField(blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    tenant_id = models.CharField(max_length=60, blank=True, db_index=True)
    # Original UUID from the source export — keeps re-imports idempotent.
    source_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "name"]

    def __str__(self):
        return f"{self.date} — {self.name}"
