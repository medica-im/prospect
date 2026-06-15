from django.contrib import admin
from .models import CompanyType, EmailTemplate, SentEmail


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
