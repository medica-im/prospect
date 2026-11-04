import csv
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db.models import Count, Max, Q
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from .models import CompanyType, EmailTemplate, ScheduledBatch, SentEmail, Unsubscribe
from .schemas import (
    CompanyEmailStats,
    CompanyOut,
    CompanyTypeOut,
    DeliveryEventOut,
    EmailTemplateOut,
    ProblemAddressOut,
    ScheduledBatchOut,
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
from .services.dispatch import dispatch_batch

logger = logging.getLogger(__name__)
router = Router()

MIN_SCHEDULE_LEAD = timedelta(minutes=1)


# --- Company Types ---

@router.get("/company-types", response=list[CompanyTypeOut])
def list_company_types(request):
    return CompanyType.objects.all()


# --- Email Stats per Company ---

def _reached():
    """The emails that count as received when choosing recipients.

    Counted: sent (no news yet), delivered, deferred (Mailgun is still retrying;
    a final failure turns it into a bounce) and complained (it was delivered).
    Not counted: sends Mailgun refused (success=False), bounced and suppressed.
    """
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

def _parse_schedule(scheduled_for: str, tz_name: str) -> datetime:
    """Turn a wall-clock time in `tz_name` into an aware UTC datetime, or raise 422.

    An ambiguous time (clocks go back, so it happens twice) resolves to its first
    occurrence; a time that does not exist (clocks go forward) is refused.
    """
    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HttpError(422, f"Unknown time zone: {tz_name}")
    try:
        local = datetime.fromisoformat(scheduled_for)
    except ValueError:
        raise HttpError(422, f"Invalid date and time: {scheduled_for}")
    if local.tzinfo is not None:
        raise HttpError(422, "scheduled_for must not carry a UTC offset; pass the zone in `timezone`")

    local = local.replace(tzinfo=zone, fold=0)
    at = local.astimezone(dt_timezone.utc)
    if at.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
        raise HttpError(422, f"{scheduled_for} does not exist in {tz_name} (clocks change)")
    if at < timezone.now() + MIN_SCHEDULE_LEAD:
        raise HttpError(422, "Choose a time at least a minute in the future")
    return at


@router.post("/emails/send", response=SendEmailResponse)
def send_emails(request, payload: SendEmailRequest):
    """Queue emails to selected companies with the chosen template, now or later.

    With `scheduled_for` the batch is stored and sent by the beat task when due;
    otherwise it is queued immediately.
    """
    template = get_object_or_404(EmailTemplate, id=payload.template_id)

    if payload.scheduled_for:
        at = _parse_schedule(payload.scheduled_for, payload.timezone)
        ScheduledBatch.objects.create(
            template=template,
            recipients=[r.dict() for r in payload.recipients],
            scheduled_at=at,
            timezone=payload.timezone,
            created_by=request.user if request.user.is_authenticated else None,
        )
        message = (
            f"Scheduled {len(payload.recipients)} email(s) for "
            f"{payload.scheduled_for.replace('T', ' ')} ({payload.timezone})."
        )
        if settings.EMAIL_DRY_RUN:
            message += " Dry run: nothing actually leaves the server."
        return SendEmailResponse(queued=0, message=message, scheduled_at=at)

    queued, blocked = dispatch_batch(template, payload.recipients)

    message = f"Queued {queued} email(s) for sending."
    if blocked:
        message += f" Skipped {len(blocked)} unsubscribed or undeliverable recipient(s)."
    if settings.EMAIL_DRY_RUN:
        message += " Dry run: nothing actually leaves the server."

    return SendEmailResponse(
        queued=queued,
        message=message,
        skipped=len(blocked),
        skipped_emails=[r.company_email for r in blocked],
    )


# --- Scheduled batches ---

def _batch_out(b: ScheduledBatch) -> ScheduledBatchOut:
    return ScheduledBatchOut(
        id=b.id,
        template_name=b.template.name if b.template else None,
        scheduled_at=b.scheduled_at,
        timezone=b.timezone,
        status=b.status,
        recipient_count=len(b.recipients),
        queued=b.queued,
        skipped=b.skipped,
        created_at=b.created_at,
    )


@router.get("/emails/scheduled", response=list[ScheduledBatchOut])
def list_scheduled_batches(request):
    return [_batch_out(b) for b in ScheduledBatch.objects.select_related("template")]


@router.post("/emails/scheduled/{batch_id}/cancel", response=ScheduledBatchOut)
def cancel_scheduled_batch(request, batch_id: int):
    batch = get_object_or_404(ScheduledBatch.objects.select_related("template"), id=batch_id)
    # Conditional update: loses cleanly against the beat task claiming it.
    cancelled = ScheduledBatch.objects.filter(
        pk=batch.pk, status=ScheduledBatch.STATUS_PENDING,
    ).update(status=ScheduledBatch.STATUS_CANCELLED)
    if not cancelled:
        raise HttpError(409, "Only a batch that is still waiting can be cancelled")
    batch.status = ScheduledBatch.STATUS_CANCELLED
    return _batch_out(batch)


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
