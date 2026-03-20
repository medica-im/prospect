from django.db import models


class CompanyType(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="Internal identifier (e.g. cpts, msp)")
    label = models.CharField(max_length=100, help_text="Display name (e.g. CPTS, MSP)")

    def __str__(self):
        return self.label


class EmailTemplate(models.Model):
    name = models.CharField(max_length=255, unique=True)
    subject_template = models.CharField(
        max_length=500,
        help_text="Jinja2 template for subject. Variables: {{ company_name }}, {{ email }}",
    )
    html_body = models.TextField(
        help_text="Pre-compiled MJML (HTML) with Jinja2 variables: {{ company_name }}, {{ email }}",
    )
    company_type = models.ForeignKey(
        CompanyType, on_delete=models.CASCADE, related_name="templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.company_type})"


class SentEmail(models.Model):
    template = models.ForeignKey(
        EmailTemplate, on_delete=models.SET_NULL, null=True, related_name="sent_emails",
    )
    company_name = models.CharField(max_length=255)
    company_email = models.EmailField()
    company_type = models.ForeignKey(
        CompanyType, on_delete=models.SET_NULL, null=True, related_name="sent_emails",
    )
    twenty_crm_id = models.CharField(max_length=255, help_text="Company ID from Twenty CRM")
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    mailgun_message_id = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.company_name} - {self.sent_at:%Y-%m-%d %H:%M}"
