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
