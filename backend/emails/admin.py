from django.contrib import admin
from .models import CompanyType, EmailTemplate, SentEmail


@admin.register(CompanyType)
class CompanyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "label")


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "company_type", "updated_at")
    list_filter = ("company_type",)
    search_fields = ("name", "subject_template")


@admin.register(SentEmail)
class SentEmailAdmin(admin.ModelAdmin):
    list_display = ("company_name", "company_email", "company_type", "success", "sent_at")
    list_filter = ("success", "company_type", "sent_at")
    search_fields = ("company_name", "company_email")
    readonly_fields = ("sent_at",)
