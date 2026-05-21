from django.db import models


class ChatLog(models.Model):
    """Every chatbot prompt request and its response, persisted to SQLite.

    This is the "prompt req & res data" store: one row per /api/chat/ call,
    including the retrieved context, citations and timing breakdown.
    """

    # Request
    question = models.TextField()
    session_id = models.CharField(max_length=80, blank=True, db_index=True)

    # Response
    answer = models.TextField(blank=True)
    sources = models.JSONField(default=list, blank=True)
    context_used = models.TextField(blank=True)

    # Models / retrieval metadata
    chat_model = models.CharField(max_length=120, blank=True)
    embed_model = models.CharField(max_length=120, blank=True)
    top_k = models.PositiveIntegerField(default=0)
    matches_found = models.PositiveIntegerField(default=0)

    # Timing (milliseconds)
    retrieval_ms = models.PositiveIntegerField(default=0)
    llm_ms = models.PositiveIntegerField(default=0)
    total_ms = models.PositiveIntegerField(default=0)

    # Outcome
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "ok" if self.success else "error"
        return f"[{status}] {self.question[:60]}"
