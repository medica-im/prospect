from django.contrib import admin

from .models import ImportRun, Transformer


@admin.register(Transformer)
class TransformerAdmin(admin.ModelAdmin):
    list_display = ("name", "company_type", "csv_delimiter", "updated_at")
    list_filter = ("company_type",)


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("id", "transformer", "company_type", "total_rows",
                    "created_count", "skipped_count", "failed_count", "created_at")
    list_filter = ("company_type", "created_at")
    readonly_fields = ("created_at",)
