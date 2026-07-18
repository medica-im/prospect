from django.contrib import admin

from .models import WebProspectRecord, WebProspectRun


class WebProspectRecordInline(admin.TabularInline):
    model = WebProspectRecord
    extra = 0
    readonly_fields = ("name", "status", "twenty_company_id", "missing_fields", "error")
    can_delete = False


@admin.register(WebProspectRun)
class WebProspectRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source_url", "scraper", "total", "created_count",
        "already_present_count", "failed_count", "created_at",
    )
    list_filter = ("scraper", "ask_confirmation", "created_at")
    inlines = [WebProspectRecordInline]


@admin.register(WebProspectRecord)
class WebProspectRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "run", "twenty_company_id")
    list_filter = ("status",)
    search_fields = ("name", "twenty_company_id")
