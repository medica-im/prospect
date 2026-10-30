import csv
import logging

from django.conf import settings
from django.db.models import Count, Max, Q
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router

from .models import CompanyType, EmailTemplate, SentEmail, Unsubscribe
from .schemas import (
    CompanyEmailStats,
    CompanyOut,
    CompanyTypeOut,
    DeliveryEventOut,
    EmailTemplateOut,
    ProblemAddressOut,
    SendEmailRequest,
    SendEmailResponse,
    SentEmailOut,
    SentEmailPreview,
    UnsubscribeOut,
)
from .services.delivery import problem_addresses
from .services.twenty_crm import fetch_companies
from .services.imap import fetch_email_from_sent
from webprospects.french import UnknownArticleError

from .services.renderer import build_context, render_template
from .services.unsubscribe import filter_recipients
from .tasks import send_prospect_email

logger = logging.getLogger(__name__)
router = Router()


# --- Company Types ---

@router.get("/company-types", response=list[CompanyTypeOut])
def list_company_types(request):
    return CompanyType.objects.all()


# --- Email Stats per Company ---

def _reached():
    """Emails Mailgun accepted and that were not refused or bounced afterwards."""
    return SentEmail.objects.filter(success=True).exclude(
        delivery_status__in=[SentEmail.DELIVERY_BOUNCED, SentEmail.DELIVERY_SUPPRESSED],
    )


@router.get("/email-stats", response=dict[str, CompanyEmailStats])
def email_stats(request):
    """Return sent email count and last sent date per company (by twenty_crm_id).

    Emails that bounced never reached anyone, so they do not count as sent.
    """
    stats = _reached().values("twenty_crm_id").annotate(
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


@router.get("/email-stats/by-address", response=dict[str, CompanyEmailStats])
def email_stats_by_address(request):
    """Return sent email count and last sent date per recipient address (lowercased).

    The per-company stats above lump every address of a company together; this
    is what lets the send page filter on how often one inbox was contacted.
    """
    stats = (
        _reached()
        .annotate(address=Lower("company_email"))
        .values("address")
        .annotate(total_sent=Count("id"), last_sent_at=Max("sent_at"))
    )
    return {
        s["address"]: CompanyEmailStats(
            total_sent=s["total_sent"], last_sent_at=s["last_sent_at"]
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
    return EmailTemplate.objects.prefetch_related("company_types").all()


# --- Send Emails ---

@router.post("/emails/send", response=SendEmailResponse)
def send_emails(request, payload: SendEmailRequest):
    """Queue emails to selected companies with the chosen template.

    Unsubscribed recipients are dropped here so the operator gets immediate
    feedback; the task re-checks before sending, which is the real gate.
    """
    template = get_object_or_404(EmailTemplate, id=payload.template_id)

    recipients, blocked = filter_recipients(payload.recipients)

    for recipient in recipients:
        send_prospect_email.delay(
            template_id=template.id,
            company_name=recipient.company_name,
            company_email=recipient.company_email,
            company_type_id=recipient.company_type_id,
            twenty_crm_id=recipient.twenty_crm_id,
        )

    message = f"Queued {len(recipients)} email(s) for sending."
    if blocked:
        logger.info(f"Skipped {len(blocked)} unsubscribed or undeliverable recipient(s)")
        message += f" Skipped {len(blocked)} unsubscribed or undeliverable recipient(s)."
    if settings.EMAIL_DRY_RUN:
        message += " Dry run: nothing actually leaves the server."

    return SendEmailResponse(
        queued=len(recipients),
        message=message,
        skipped=len(blocked),
        skipped_emails=[r.company_email for r in blocked],
    )


# --- Unsubscribes ---

@router.get("/unsubscribes", response=list[UnsubscribeOut])
def list_unsubscribes(request):
    """Suppression list, consumed by the frontend to flag opted-out addresses."""
    return Unsubscribe.objects.all()


# --- Sent Emails ---

@router.get("/emails/sent", response=list[SentEmailOut])
def list_sent_emails(
    request,
    company_type_id: int | None = None,
    success: bool | None = None,
    delivery: str | None = None,
):
    """List sent emails with optional filters.

    `delivery` is a delivery status (delivered, bounced, ...), a bounce class
    (mailbox_missing, ...), or "problem" for everything that needs a look: a
    failed send, a bounce, a refusal or a spam complaint.
    """
    qs = SentEmail.objects.select_related("template", "company_type").all()

    if company_type_id is not None:
        qs = qs.filter(company_type_id=company_type_id)
    if success is not None:
        qs = qs.filter(success=success)
    if delivery == "problem":
        qs = qs.filter(
            Q(success=False) | Q(delivery_status__in=[
                SentEmail.DELIVERY_BOUNCED,
                SentEmail.DELIVERY_SUPPRESSED,
                SentEmail.DELIVERY_COMPLAINED,
            ])
        )
    elif delivery:
        qs = qs.filter(Q(delivery_status=delivery) | Q(bounce_class=delivery))

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
            delivery_status=email.delivery_status,
            bounce_class=email.bounce_class,
            delivery_detail=email.delivery_detail,
            delivery_updated_at=email.delivery_updated_at,
        ))
    return results


# --- Problem addresses (to fix in the CRM) ---

CSV_COLUMNS = [
    ("address", "address"),
    ("company_name", "company"),
    ("twenty_crm_id", "twenty_id"),
    ("delivery_status", "status"),
    ("bounce_class", "problem"),
    ("delivery_detail", "smtp_detail"),
    ("last_event_at", "date"),
    ("emails_sent", "emails_sent"),
]


@router.get("/emails/problem-addresses", response=list[ProblemAddressOut])
def list_problem_addresses(request, all: bool = False):
    """Addresses to fix in the CRM: mailbox/domain does not exist, refused, or spam complaint.

    all=true adds the merely troublesome ones (full mailbox, policy block, ...).
    """
    return problem_addresses(dead_only=not all)


@router.get("/emails/problem-addresses.csv")
def export_problem_addresses(request, all: bool = False):
    """Same list as a CSV download. BOM-prefixed so Excel reads accents correctly."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="adresses-a-corriger.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow([header for _, header in CSV_COLUMNS])
    for row in problem_addresses(dead_only=not all):
        writer.writerow([
            row[key].isoformat() if key == "last_event_at" and row[key] else row[key]
            for key, _ in CSV_COLUMNS
        ])
    return response


# --- Sent Email Preview from IMAP ---

@router.get("/emails/sent/{sent_email_id}/preview", response=SentEmailPreview)
def preview_sent_email(request, sent_email_id: int):
    """Fetch actual sent email HTML from IMAP Sent folder."""
    sent_email = get_object_or_404(SentEmail, id=sent_email_id)

    # Reconstruct the same context used at send time. For a historical preview we
    # tolerate an unknown article (the email was already sent) and fall back.
    try:
        context = build_context(sent_email.company_name, sent_email.company_email)
    except UnknownArticleError:
        context = {
            "company_name": sent_email.company_name,
            "email": sent_email.company_email,
            "definite_article_company_name": sent_email.company_name,
        }
    subject = render_template(sent_email.template.subject_template, context)

    # Format date for IMAP search (DD-Mon-YYYY)
    sent_date = sent_email.sent_at.strftime("%d-%b-%Y")

    # An unconfigured (dev) or unreachable mailbox must not break the page: the
    # re-rendered template below is a faithful enough stand-in.
    html_body = None
    if settings.IMAP_SERVER:
        try:
            html_body = fetch_email_from_sent(subject=subject, sent_date=sent_date)
        except Exception:
            logger.warning("IMAP lookup failed for sent email %s", sent_email.id, exc_info=True)

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
        success=sent_email.success,
        error_message=sent_email.error_message,
        delivery_status=sent_email.delivery_status,
        bounce_class=sent_email.bounce_class,
        delivery_detail=sent_email.delivery_detail,
        delivery_updated_at=sent_email.delivery_updated_at,
        events=[DeliveryEventOut.from_orm(event) for event in sent_email.events.all()],
    )
