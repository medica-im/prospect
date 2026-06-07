from django.db import models

from emails.models import CompanyType


class Transformer(models.Model):
    """Reusable CSV-to-Twenty CRM column mapping."""
    name = models.CharField(max_length=255, unique=True,
        help_text="Descriptive name, e.g. 'CPTS CSV 2024'")
    company_type = models.ForeignKey(
        CompanyType, on_delete=models.CASCADE, related_name="transformers")
    csv_name_column = models.CharField(max_length=255,
        help_text="CSV column for company name")
    csv_email_column = models.CharField(max_length=255,
        help_text="CSV column for email")
    csv_postcode_column = models.CharField(max_length=255,
        help_text="CSV column for postal code (first 2 chars used)")
    csv_domain_column = models.CharField(max_length=255, blank=True, default="",
        help_text="CSV column for domain (optional)")
    csv_delimiter = models.CharField(max_length=5, default=";",
        help_text="CSV field delimiter")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.company_type})"


class ImportRun(models.Model):
    """Records each import execution for auditing."""
    transformer = models.ForeignKey(
        Transformer, on_delete=models.SET_NULL, null=True, related_name="import_runs")
    company_type = models.ForeignKey(
        CompanyType, on_delete=models.SET_NULL, null=True)
    total_rows = models.IntegerField(default=0)
    deduplicated_count = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.id} - {self.created_at:%Y-%m-%d %H:%M}"
