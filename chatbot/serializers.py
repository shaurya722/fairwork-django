from rest_framework import serializers

from .models import ChatLog


class ChatRequestSerializer(serializers.Serializer):
    """Validates an incoming /api/chat/ request body."""

    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    session_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=15)


class ScrapeRequestSerializer(serializers.Serializer):
    """Validates an incoming /api/scrape/ request body — every field optional."""

    url = serializers.URLField(required=False, allow_blank=True, default="")
    code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    fresh = serializers.BooleanField(required=False, default=False)


class NDISChatRequestSerializer(serializers.Serializer):
    """Validates an incoming /api/ndis-chat/ request body."""

    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    session_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=15)
    # Optional year override (e.g. "2024-25"). Defaults to the active document
    # for the latest year so the API always answers from the current pricing.
    year = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )


class ShiftCalcRequestSerializer(serializers.Serializer):
    """Validates a /api/shift-calc/ request body.

    The full Shift Lifecycle Payload schema is enforced by the LLM prompt
    itself (see ``services.llm.SHIFT_CALC_SYSTEM_PROMPT``); here we just
    accept the structured payload as a dict plus a handful of top-level
    helpers (the worker's base rate, an optional shift id and session id).
    """

    shift_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    employee_base_rate = serializers.FloatField(required=False)
    session_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    # Full Shift Lifecycle Payload dict — passed straight to the prompt.
    shift_lifecycle_payload = serializers.JSONField()


class ChatLogSerializer(serializers.ModelSerializer):
    """Serialises a stored chat request/response row."""

    class Meta:
        model = ChatLog
        fields = [
            "id",
            "question",
            "answer",
            "sources",
            "session_id",
            "chat_model",
            "embed_model",
            "top_k",
            "matches_found",
            "retrieval_ms",
            "llm_ms",
            "total_ms",
            "success",
            "error",
            "created_at",
        ]


class SessionSummarySerializer(serializers.Serializer):
    """Serialises a single chat session summary for the sessions listing API.

    Used by GET /api/chat/sessions/ to power a chat history sidebar.
    """
    session_id = serializers.CharField()
    message_count = serializers.IntegerField()
    last_message_at = serializers.DateTimeField()
    preview = serializers.CharField(allow_blank=True, allow_null=True, required=False)
