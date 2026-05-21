from django.contrib import admin

from .models import AwardClause, PublicHoliday


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
