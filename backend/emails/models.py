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
        help_text=(
            "Jinja2 template for subject. Variables: {{ company_name }}, {{ email }}, "
            "{{ definite_article_company_name }} (name with French article, e.g. "
            "'la MSP du Marais')"
        ),
    )
    html_body = models.TextField(
        help_text=(
            "Pre-compiled MJML (HTML) with Jinja2 variables: {{ company_name }}, "
            "{{ email }}, {{ definite_article_company_name }}, {{ unsubscribe_url }}. "
            "Every template MUST include an unsubscribe link, e.g. "
            '<a href="{{ unsubscribe_url }}">Se désabonner</a> — if it is missing, a '
            "plain footer is appended automatically at send time."
        ),
    )
    company_types = models.ManyToManyField(
        CompanyType, related_name="templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({', '.join(ct.label for ct in self.company_types.all())})"


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


class Unsubscribe(models.Model):
    """An email address that opted out. Sending to it is refused forever.

    The address itself is never deleted or hidden — it stays visible in the
    prospect list (it is public data on the CRM side), it is only marked as
    unsubscribed and made unselectable.
    """

    SOURCE_LINK = "link"
    SOURCE_LIST_HEADER = "list_header"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_LINK, "Unsubscribe link"),
        (SOURCE_LIST_HEADER, "List-Unsubscribe one-click"),
        (SOURCE_MANUAL, "Manual (admin)"),
    ]

    email = models.EmailField(unique=True, db_index=True)
    unsubscribed_at = models.DateTimeField(auto_now_add=True)
    sent_email = models.ForeignKey(
        SentEmail,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unsubscribes",
        help_text="The email whose link triggered this unsubscribe",
    )
    company_name = models.CharField(max_length=255, blank=True, default="")
    twenty_crm_id = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LINK)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-unsubscribed_at"]

    def __str__(self):
        return f"{self.email} ({self.unsubscribed_at:%Y-%m-%d})"
