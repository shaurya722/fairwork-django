from django.contrib import admin

from .models import ChatLog


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "question",
        "success",
        "matches_found",
        "total_ms",
        "created_at",
    )
    list_filter = ("success", "chat_model", "created_at")
    search_fields = ("question", "answer", "session_id")
    readonly_fields = tuple(
        f.name for f in ChatLog._meta.fields if f.name != "id"
    )
