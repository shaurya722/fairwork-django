from django.contrib import admin

from .models import AwardClause, NDISChunk, NDISDocument, PublicHoliday


@admin.register(AwardClause)
class AwardClauseAdmin(admin.ModelAdmin):
    list_display = (
        "award_code",
        "clause_no",
        "chunk_index",
        "title",
        "token_estimate",
        "is_indexed",
    )
    list_filter = ("award_code", "is_indexed", "part")
    search_fields = ("clause_no", "title", "content")
    readonly_fields = ("created_at", "updated_at", "indexed_at", "vector_id")


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "tenant_id", "source_url")
    list_filter = ("tenant_id",)
    search_fields = ("name", "information")
    date_hierarchy = "date"
    ordering = ("date",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(NDISDocument)
class NDISDocumentAdmin(admin.ModelAdmin):
    list_display = ("year", "version", "title", "is_active", "page_count", "chunk_count")
    list_filter = ("year", "is_active")
    search_fields = ("year", "version", "title", "source_file")
    readonly_fields = ("created_at", "updated_at", "page_count", "chunk_count")


@admin.register(NDISChunk)
class NDISChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "section", "page_start", "is_indexed")
    list_filter = ("document__year", "is_indexed")
    search_fields = ("section", "content")
    readonly_fields = ("created_at", "updated_at", "indexed_at", "vector_id")
