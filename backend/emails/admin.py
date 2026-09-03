from django.contrib import admin
from .models import CompanyType, EmailTemplate, SentEmail, Unsubscribe


@admin.register(CompanyType)
class CompanyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "label")


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "get_company_types", "updated_at")
    list_filter = ("company_types",)
    filter_horizontal = ("company_types",)
    search_fields = ("name", "subject_template")

    @admin.display(description="Company Types")
    def get_company_types(self, obj):
        return ", ".join(ct.label for ct in obj.company_types.all())


@admin.register(SentEmail)
class SentEmailAdmin(admin.ModelAdmin):
    list_display = ("company_name", "company_email", "company_type", "success", "sent_at")
    list_filter = ("success", "company_type", "sent_at")
    search_fields = ("company_name", "company_email")
    readonly_fields = ("sent_at",)


@admin.register(Unsubscribe)
class UnsubscribeAdmin(admin.ModelAdmin):
    """Also the entry point for opt-outs received by reply: add source=manual."""

    list_display = ("email", "unsubscribed_at", "company_name", "source")
    list_filter = ("source", "unsubscribed_at")
    search_fields = ("email", "company_name", "twenty_crm_id")
    readonly_fields = ("unsubscribed_at",)
    autocomplete_fields = ("sent_email",)
