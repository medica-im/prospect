from datetime import datetime

from ninja import Schema


# --- Company Types ---

class CompanyTypeOut(Schema):
    id: int
    name: str
    label: str


# --- Twenty CRM Companies ---

class PeopleOut(Schema):
    id: str
    name: str
    email: str
    created_at: str


class CompanyOut(Schema):
    id: str
    name: str
    emails: list[str]
    company_type: str | None = None
    domain: str
    city: str
    created_at: str
    people: list[PeopleOut] = []


# --- Templates ---

class EmailTemplateOut(Schema):
    id: int
    name: str
    subject_template: str
    company_types: list[CompanyTypeOut]


# --- Send ---

class SendEmailRecipient(Schema):
    company_name: str
    company_email: str
    company_type_id: int
    twenty_crm_id: str


class SendEmailRequest(Schema):
    template_id: int
    recipients: list[SendEmailRecipient]
    # Wall-clock time in `timezone`, naive ISO "YYYY-MM-DDTHH:MM". Unset = send now.
    scheduled_for: str | None = None
    timezone: str = "Europe/Paris"


class SendEmailResponse(Schema):
    queued: int
    message: str
    skipped: int = 0
    skipped_emails: list[str] = []
    scheduled_at: datetime | None = None


class ScheduledBatchOut(Schema):
    id: int
    template_name: str | None = None
    scheduled_at: datetime
    timezone: str
    status: str
    recipient_count: int
    queued: int
    skipped: int
    created_at: datetime


# --- Sent Emails ---

class SentEmailOut(Schema):
    id: int
    company_name: str
    company_email: str
    company_type: CompanyTypeOut | None = None
    template_name: str | None = None
    sent_at: datetime
    success: bool
    mailgun_message_id: str
    error_message: str
    delivery_status: str
    bounce_class: str
    delivery_detail: str
    delivery_updated_at: datetime | None = None


class ProblemAddressOut(Schema):
    """An address whose last conclusive delivery result is a problem."""

    address: str
    company_name: str
    twenty_crm_id: str
    delivery_status: str
    bounce_class: str
    delivery_detail: str
    last_event_at: datetime | None = None
    emails_sent: int


class DeliveryEventOut(Schema):
    kind: str
    severity: str
    smtp_code: str
    enhanced_code: str
    reason: str
    detail: str
    occurred_at: datetime


class CompanyEmailStats(Schema):
    total_sent: int
    last_sent_at: datetime | None = None


# --- Unsubscribes ---

class UnsubscribeOut(Schema):
    email: str
    unsubscribed_at: datetime
    company_name: str
    twenty_crm_id: str
    source: str


class SentEmailPreview(Schema):
    id: int
    subject: str
    html_body: str
    sent_at: datetime
    mailgun_message_id: str
    from_email: str
    to_email: str
    success: bool
    error_message: str
    delivery_status: str
    bounce_class: str
    delivery_detail: str
    delivery_updated_at: datetime | None = None
    events: list[DeliveryEventOut] = []
