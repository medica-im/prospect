from datetime import datetime

from ninja import Schema


# --- Company Types ---

class CompanyTypeOut(Schema):
    id: int
    name: str
    label: str


# --- Twenty CRM Companies ---

class CompanyOut(Schema):
    id: str
    name: str
    emails: list[str]
    company_type: str | None = None
    domain: str
    city: str


# --- Templates ---

class EmailTemplateOut(Schema):
    id: int
    name: str
    subject_template: str
    company_type: CompanyTypeOut


# --- Send ---

class SendEmailRecipient(Schema):
    company_name: str
    company_email: str
    company_type_id: int
    twenty_crm_id: str


class SendEmailRequest(Schema):
    template_id: int
    recipients: list[SendEmailRecipient]


class SendEmailResponse(Schema):
    queued: int
    message: str


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


class SentEmailPreview(Schema):
    id: int
    subject: str
    html_body: str
    sent_at: datetime
    mailgun_message_id: str
    from_email: str
    to_email: str
