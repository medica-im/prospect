import logging

from django.conf import settings
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from ninja import Router

from .models import CompanyType, EmailTemplate, SentEmail
from .schemas import (
    CompanyEmailStats,
    CompanyOut,
    CompanyTypeOut,
    EmailTemplateOut,
    SendEmailRequest,
    SendEmailResponse,
    SentEmailOut,
    SentEmailPreview,
)
from .services.twenty_crm import fetch_companies
from .services.imap import fetch_email_from_sent
from .services.renderer import render_template
from .tasks import send_prospect_email

logger = logging.getLogger(__name__)
router = Router()


# --- Company Types ---

@router.get("/company-types", response=list[CompanyTypeOut])
def list_company_types(request):
    return CompanyType.objects.all()


# --- Email Stats per Company ---

@router.get("/email-stats", response=dict[str, CompanyEmailStats])
def email_stats(request, twenty_crm_ids: str = ""):
    """Return sent email count and last sent date per company (by twenty_crm_id)."""
    ids = [i.strip() for i in twenty_crm_ids.split(",") if i.strip()]
    qs = SentEmail.objects.filter(success=True)
    if ids:
        qs = qs.filter(twenty_crm_id__in=ids)
    stats = qs.values("twenty_crm_id").annotate(
        total_sent=Count("id"),
        last_sent_at=Max("sent_at"),
    )
    return {
        s["twenty_crm_id"]: CompanyEmailStats(
            total_sent=s["total_sent"],
            last_sent_at=s["last_sent_at"],
        )
        for s in stats
    }


# --- Companies (Twenty CRM proxy) ---

@router.get("/companies", response=list[CompanyOut])
def list_companies(request):
    """Fetch companies from Twenty CRM."""
    return fetch_companies()


# --- Templates ---

@router.get("/templates", response=list[EmailTemplateOut])
def list_templates(request):
    return EmailTemplate.objects.select_related("company_type").all()


# --- Send Emails ---

@router.post("/emails/send", response=SendEmailResponse)
def send_emails(request, payload: SendEmailRequest):
    """Queue emails to selected companies with the chosen template."""
    template = get_object_or_404(EmailTemplate, id=payload.template_id)

    for recipient in payload.recipients:
        send_prospect_email.delay(
            template_id=template.id,
            company_name=recipient.company_name,
            company_email=recipient.company_email,
            company_type_id=recipient.company_type_id,
            twenty_crm_id=recipient.twenty_crm_id,
        )

    return SendEmailResponse(
        queued=len(payload.recipients),
        message=f"Queued {len(payload.recipients)} email(s) for sending.",
    )


# --- Sent Emails ---

@router.get("/emails/sent", response=list[SentEmailOut])
def list_sent_emails(
    request,
    company_type_id: int | None = None,
    success: bool | None = None,
):
    """List sent emails with optional filters."""
    qs = SentEmail.objects.select_related("template", "company_type").all()

    if company_type_id is not None:
        qs = qs.filter(company_type_id=company_type_id)
    if success is not None:
        qs = qs.filter(success=success)

    results = []
    for email in qs:
        results.append(SentEmailOut(
            id=email.id,
            company_name=email.company_name,
            company_email=email.company_email,
            company_type=CompanyTypeOut.from_orm(email.company_type) if email.company_type else None,
            template_name=email.template.name if email.template else None,
            sent_at=email.sent_at,
            success=email.success,
            mailgun_message_id=email.mailgun_message_id,
            error_message=email.error_message,
        ))
    return results


# --- Sent Email Preview from IMAP ---

@router.get("/emails/sent/{sent_email_id}/preview", response=SentEmailPreview)
def preview_sent_email(request, sent_email_id: int):
    """Fetch actual sent email HTML from IMAP Sent folder."""
    sent_email = get_object_or_404(SentEmail, id=sent_email_id)

    context = {"company_name": sent_email.company_name, "email": sent_email.company_email}
    subject = render_template(sent_email.template.subject_template, context)

    # Format date for IMAP search (DD-Mon-YYYY)
    sent_date = sent_email.sent_at.strftime("%d-%b-%Y")

    html_body = fetch_email_from_sent(subject=subject, sent_date=sent_date)

    if html_body is None:
        # Fallback: re-render from template
        html_body = render_template(sent_email.template.html_body, context)

    return SentEmailPreview(
        id=sent_email.id,
        subject=subject,
        html_body=html_body,
        sent_at=sent_email.sent_at,
        mailgun_message_id=sent_email.mailgun_message_id,
        from_email=settings.MAILGUN_FROM_EMAIL,
        to_email=sent_email.company_email,
    )
