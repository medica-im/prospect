from django.conf import settings
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
    # True once Mailgun *accepted* the message. What happens to it afterwards is
    # tracked by delivery_status, fed by Mailgun's webhooks (services/delivery.py).
    success = models.BooleanField(default=False)
    mailgun_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    error_message = models.TextField(blank=True, default="")

    DELIVERY_SENT = "sent"
    DELIVERY_DELIVERED = "delivered"
    DELIVERY_DEFERRED = "deferred"
    DELIVERY_BOUNCED = "bounced"
    DELIVERY_SUPPRESSED = "suppressed"
    DELIVERY_COMPLAINED = "complained"
    DELIVERY_CHOICES = [
        (DELIVERY_SENT, "Accepted by Mailgun"),
        (DELIVERY_DELIVERED, "Delivered"),
        (DELIVERY_DEFERRED, "Delayed (temporary failure)"),
        (DELIVERY_BOUNCED, "Bounced (permanent failure)"),
        (DELIVERY_SUPPRESSED, "Refused (address on Mailgun suppression list)"),
        (DELIVERY_COMPLAINED, "Reported as spam"),
    ]

    BOUNCE_MAILBOX_MISSING = "mailbox_missing"
    BOUNCE_DOMAIN_MISSING = "domain_missing"
    BOUNCE_MAILBOX_FULL = "mailbox_full"
    BOUNCE_BLOCKED = "blocked"
    BOUNCE_OTHER = "other"
    BOUNCE_CHOICES = [
        (BOUNCE_MAILBOX_MISSING, "Mailbox does not exist"),
        (BOUNCE_DOMAIN_MISSING, "Domain does not exist or has no mail server"),
        (BOUNCE_MAILBOX_FULL, "Mailbox full"),
        (BOUNCE_BLOCKED, "Rejected by the recipient's server (policy / spam)"),
        (BOUNCE_OTHER, "Other permanent failure"),
    ]

    delivery_status = models.CharField(
        max_length=20, choices=DELIVERY_CHOICES, default=DELIVERY_SENT, db_index=True,
    )
    bounce_class = models.CharField(
        max_length=20, choices=BOUNCE_CHOICES, blank=True, default="",
        help_text="Why a bounced email failed. Only set when delivery_status is bounced.",
    )
    delivery_detail = models.TextField(
        blank=True, default="",
        help_text="SMTP code and message reported by the recipient's server",
    )
    delivery_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.company_name} - {self.sent_at:%Y-%m-%d %H:%M}"


class ScheduledBatch(models.Model):
    """A send batch held in the database until `scheduled_at`.

    Postgres is the source of truth, not the broker: a batch scheduled days ahead
    must survive restarts and be cancellable, which a Celery `eta` task is not.
    The beat task `emails.tasks.dispatch_due_batches` turns due batches into the
    usual per-recipient `send_prospect_email` tasks.
    """

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Waiting for its send time"),
        (STATUS_RUNNING, "Being queued"),
        (STATUS_DONE, "Queued for sending"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    template = models.ForeignKey(
        EmailTemplate, on_delete=models.SET_NULL, null=True, related_name="scheduled_batches",
    )
    recipients = models.JSONField(
        help_text="List of {company_name, company_email, company_type_id, twenty_crm_id}",
    )
    scheduled_at = models.DateTimeField(db_index=True, help_text="Send time, stored in UTC")
    timezone = models.CharField(
        max_length=64,
        help_text="IANA zone the operator picked; only used to display scheduled_at",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    queued = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"Batch {self.pk} at {self.scheduled_at:%Y-%m-%d %H:%M} UTC ({self.status})"


class DeliveryEvent(models.Model):
    """One event reported by Mailgun about a SentEmail. Append-only history.

    The unique `provider_event_id` makes webhook retries and backfill re-runs
    idempotent: inserting the same event twice fails, and the caller then knows
    to skip it.
    """

    sent_email = models.ForeignKey(
        SentEmail, on_delete=models.CASCADE, related_name="events",
    )
    provider_event_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=30, help_text="Mailgun event name: delivered, failed, complained")
    severity = models.CharField(max_length=20, blank=True, default="", help_text="permanent or temporary")
    smtp_code = models.CharField(max_length=10, blank=True, default="")
    enhanced_code = models.CharField(max_length=10, blank=True, default="", help_text="e.g. 5.1.1")
    reason = models.CharField(max_length=255, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    recipient = models.EmailField(blank=True, default="")
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    raw = models.JSONField(default=dict)

    class Meta:
        ordering = ["occurred_at", "id"]

    def __str__(self):
        return f"{self.kind} {self.recipient} ({self.occurred_at:%Y-%m-%d %H:%M})"


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
