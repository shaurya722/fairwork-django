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


class NDISDocument(models.Model):
    """A published NDIS Pricing Arrangements & Price Limits document.

    Stored per year (e.g. "2024-25") so we can keep older versions alongside
    the current one. A ``ndis_chat`` query defaults to the active document for
    the latest year unless a specific year is requested.
    """

    year = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Fiscal year label, e.g. '2024-25'.",
    )
    version = models.CharField(max_length=40, blank=True, help_text="e.g. 'v1.3'.")
    title = models.CharField(max_length=300, blank=True)
    source_file = models.CharField(
        max_length=500, blank=True,
        help_text="Original filename / path of the ingested PDF.",
    )
    source_url = models.URLField(max_length=500, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Only active documents are searched by the NDIS chat endpoint.",
    )

    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["year", "version"],
                name="unique_ndis_year_version",
            )
        ]

    def __str__(self):
        label = f"NDIS {self.year}"
        if self.version:
            label += f" {self.version}"
        return label

    @property
    def pinecone_namespace(self) -> str:
        """Per-year Pinecone namespace so each year is independently queryable."""
        slug = (self.year or "unknown").lower().replace(" ", "-")
        return f"ndis-{slug}"


class NDISChunk(models.Model):
    """A single retrievable chunk of an :class:`NDISDocument`.

    Mirrors :class:`AwardClause` — text in SQLite, embedding in Pinecone, with
    ``vector_id`` linking the two. The chunk's parent document holds the year
    and version metadata.
    """

    document = models.ForeignKey(
        NDISDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    section = models.CharField(max_length=300, blank=True)
    page_start = models.PositiveIntegerField(default=0)
    page_end = models.PositiveIntegerField(default=0)
    chunk_index = models.PositiveIntegerField(default=0)
    content = models.TextField()
    token_estimate = models.PositiveIntegerField(default=0)

    vector_id = models.CharField(max_length=160, blank=True, db_index=True)
    is_indexed = models.BooleanField(default=False)
    indexed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_ndis_doc_chunk",
            )
        ]

    def __str__(self):
        return f"{self.document} #{self.chunk_index} {self.section}"[:90]


class Document(models.Model):
    """Generic document storage for policies, procedures, training materials, etc.
    
    Supports multiple document types with isolated Pinecone namespaces.
    """
    
    DOCUMENT_TYPES = [
        ('ndis', 'NDIS Pricing Document'),
        ('policy', 'Company Policy'),
        ('procedure', 'Standard Operating Procedure'),
        ('training', 'Training Material'),
        ('reference', 'Reference Document'),
        ('other', 'Other Document'),
    ]
    
    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPES,
        default='other',
        db_index=True,
        help_text='Category/type of the document'
    )
    title = models.CharField(max_length=300)
    year = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text="Fiscal year or version identifier (e.g., '2024-25')"
    )
    version = models.CharField(max_length=40, blank=True, help_text="e.g., 'v1.3'")
    description = models.TextField(blank=True)
    source_file = models.CharField(
        max_length=500,
        blank=True,
        help_text='Original filename of the uploaded document'
    )
    source_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text='Only active documents are searched by the chatbot'
    )
    
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    namespace = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Pinecone namespace for this document's vectors"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document_type', 'is_active']),
            models.Index(fields=['namespace']),
        ]
    
    def __str__(self):
        return f"[{self.document_type.upper()}] {self.title}"[:90]
    
    def generate_namespace(self) -> str:
        """Generate Pinecone namespace: {type}-{year}-{title_slug}"""
        import re
        from django.utils.text import slugify
        
        parts = [self.document_type]
        if self.year:
            parts.append(self.year.replace('/', '-'))
        
        title_slug = slugify(self.title)[:40]
        if title_slug:
            parts.append(title_slug)
        
        return '-'.join(parts).lower()


class DocumentChunk(models.Model):
    """A single retrievable chunk of a Document.
    
    Mirrors AwardClause and NDISChunk — text in SQLite, embedding in Pinecone.
    """
    
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='chunks'
    )
    section = models.CharField(max_length=300, blank=True)
    page_start = models.PositiveIntegerField(default=0)
    page_end = models.PositiveIntegerField(default=0)
    chunk_index = models.PositiveIntegerField(default=0)
    content = models.TextField()
    token_estimate = models.PositiveIntegerField(default=0)
    
    vector_id = models.CharField(max_length=160, blank=True, db_index=True)
    is_indexed = models.BooleanField(default=False)
    indexed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['document_id', 'chunk_index']
        indexes = [
            models.Index(fields=['vector_id']),
            models.Index(fields=['is_indexed']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'chunk_index'],
                name='unique_doc_chunk'
            )
        ]
    
    def __str__(self):
        return f"{self.document} #{self.chunk_index} {self.section}"[:90]
