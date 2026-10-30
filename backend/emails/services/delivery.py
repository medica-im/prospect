"""What happened to an email after Mailgun accepted it.

Mailgun reports delivery, bounces and spam complaints through webhooks (and,
for the backfill command, through its Events and suppression-list APIs). Both
produce the same `event-data` shape, parsed here into a `ParsedEvent` and applied
to the matching `SentEmail`.

"Delivered" only means the recipient's mail server accepted the message. It does
not prove the mailbox exists (catch-all domains accept everything, and some
servers bounce later), so the UI never calls a delivered address "valid".
"""

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from django.conf import settings
from django.db import IntegrityError, transaction

from ..models import DeliveryEvent, SentEmail
from .unsubscribe import normalize

logger = logging.getLogger(__name__)

# Mailgun retries a failed webhook for up to 8 hours and may not re-sign it, so
# a signature is accepted for longer than that. Events are idempotent anyway.
SIGNATURE_MAX_AGE_SECONDS = 12 * 3600
SIGNATURE_MAX_FUTURE_SECONDS = 300

# `failed` events caused by Mailgun refusing to send because the address is on
# its own suppression list (an earlier bounce, complaint or unsubscribe).
SUPPRESSION_REASONS = {"suppress-bounce", "suppress-complaint", "suppress-unsubscribe"}

_ENHANCED_CODE = re.compile(r"\b([245])\.(\d{1,3})\.(\d{1,3})\b")

# 5.1.1 bad mailbox, 5.1.0 generic bad address, 5.1.10 Microsoft "recipient not found".
_MAILBOX_MISSING_CODES = ("5.1.0", "5.1.1", "5.1.10")
_MAILBOX_MISSING_WORDS = (
    "user unknown", "unknown user", "no such user", "does not exist",
    "doesn't exist", "mailbox not found", "mailbox unavailable",
    "invalid recipient", "unknown recipient", "recipient not found",
    "user doesn't have", "account has been disabled", "account disabled",
)
_BLOCKED_WORDS = ("spam", "blocked", "blacklist", "blocklist", "policy")
_DOMAIN_MISSING_WORDS = (
    "domain not found", "domain does not exist", "host not found", "no mx",
    "nxdomain", "unrouteable address", "unroutable address",
)
_MAILBOX_FULL_WORDS = ("mailbox full", "over quota", "quota exceeded", "mailbox is full")


@dataclass
class ParsedEvent:
    event_id: str
    kind: str  # Mailgun event name: delivered, failed, complained, ...
    recipient: str
    occurred_at: datetime
    severity: str = ""
    reason: str = ""
    smtp_code: str = ""
    enhanced_code: str = ""
    detail: str = ""
    message_id: str = ""
    sent_email_id: int | None = None
    raw: dict = field(default_factory=dict)


# --- Signature ---------------------------------------------------------------

def verify_signature(payload: dict, now: float | None = None) -> bool:
    """Mailgun signs HMAC-SHA256(signing key, timestamp + token) in hex."""
    key = settings.MAILGUN_WEBHOOK_SIGNING_KEY
    signature = payload.get("signature") if isinstance(payload, dict) else None
    if not key or not isinstance(signature, dict):
        return False

    timestamp, token, given = (str(signature.get(k, "")) for k in ("timestamp", "token", "signature"))
    if not (timestamp and token and given):
        return False

    try:
        age = (now if now is not None else time.time()) - int(timestamp)
    except ValueError:
        return False
    if age > SIGNATURE_MAX_AGE_SECONDS or age < -SIGNATURE_MAX_FUTURE_SECONDS:
        return False

    expected = hmac.new(key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


# --- Classification ----------------------------------------------------------

def extract_enhanced_code(*texts: str) -> str:
    """First RFC 3463 status code (e.g. 5.1.1) found in the given texts."""
    for text in texts:
        match = _ENHANCED_CODE.search(text or "")
        if match:
            return ".".join(match.groups())
    return ""


def classify_failure(
    severity: str, reason: str, smtp_code: str, enhanced_code: str, detail: str,
) -> tuple[str, str]:
    """Map a Mailgun `failed` event to (SentEmail.delivery_status, bounce_class).

    Mailgun's own `severity` decides hard vs soft. Only for a hard failure do we
    look at the SMTP detail to tell "this mailbox does not exist" (the case that
    means the CRM holds a bad address) from a full mailbox or a policy block.
    """
    if reason in SUPPRESSION_REASONS:
        return SentEmail.DELIVERY_SUPPRESSED, ""
    if severity == "temporary":
        return SentEmail.DELIVERY_DEFERRED, ""

    text = (detail or "").lower()

    if enhanced_code == "5.1.2" or any(word in text for word in _DOMAIN_MISSING_WORDS):
        return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_DOMAIN_MISSING

    if enhanced_code == "5.2.2" or any(word in text for word in _MAILBOX_FULL_WORDS):
        return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_FULL

    # An explicit "no such mailbox" code beats keyword guesses below.
    if enhanced_code in _MAILBOX_MISSING_CODES:
        return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING

    if enhanced_code.startswith("5.7.") or any(word in text for word in _BLOCKED_WORDS):
        return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_BLOCKED

    if any(word in text for word in _MAILBOX_MISSING_WORDS):
        return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING

    return SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_OTHER


def next_status(current: str, incoming: str) -> str:
    """Status after an event. Events can arrive late or out of order.

    A spam complaint always wins; bounced, suppressed and complained are final;
    a late "deferred" never undoes "delivered".
    """
    final = {SentEmail.DELIVERY_BOUNCED, SentEmail.DELIVERY_SUPPRESSED, SentEmail.DELIVERY_COMPLAINED}
    if incoming == SentEmail.DELIVERY_COMPLAINED:
        return incoming
    if current in final:
        return current
    if incoming == SentEmail.DELIVERY_DEFERRED and current == SentEmail.DELIVERY_DELIVERED:
        return current
    return incoming


# --- Parsing -----------------------------------------------------------------

def normalize_message_id(message_id: str) -> str:
    """Mailgun returns ids with <angle brackets> at send time and without in events."""
    return (message_id or "").strip().strip("<>")


def _occurred_at(event_data: dict) -> datetime:
    try:
        return datetime.fromtimestamp(float(event_data["timestamp"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return datetime.now(tz=timezone.utc)


def parse_event(event_data: dict) -> ParsedEvent | None:
    """Parse Mailgun `event-data` (webhook body or Events API item).

    Returns None for events we do not track (opened, clicked, accepted, ...).
    """
    if not isinstance(event_data, dict):
        return None
    kind = event_data.get("event")
    if kind not in ("delivered", "failed", "complained"):
        return None

    status = event_data.get("delivery-status") or {}
    message = str(status.get("message") or status.get("description") or "")
    smtp_code = str(status.get("code") or "")
    enhanced = str(status.get("enhanced-code") or "") or extract_enhanced_code(message)
    detail = " ".join(part for part in (smtp_code, message) if part)

    headers = (event_data.get("message") or {}).get("headers") or {}
    message_id = normalize_message_id(headers.get("message-id", ""))

    variables = event_data.get("user-variables") or {}
    try:
        sent_email_id = int(variables.get("sent_email_id"))
    except (TypeError, ValueError):
        sent_email_id = None

    occurred_at = _occurred_at(event_data)
    recipient = normalize(event_data.get("recipient", ""))
    event_id = str(event_data.get("id") or "") or f"{message_id}:{kind}:{occurred_at.timestamp()}"

    return ParsedEvent(
        event_id=event_id,
        kind=kind,
        recipient=recipient,
        occurred_at=occurred_at,
        severity=str(event_data.get("severity") or ""),
        reason=str(event_data.get("reason") or ""),
        smtp_code=smtp_code,
        enhanced_code=enhanced,
        detail=detail,
        message_id=message_id,
        sent_email_id=sent_email_id,
        raw=event_data,
    )


# --- Applying ----------------------------------------------------------------

def find_sent_email(event: ParsedEvent) -> SentEmail | None:
    """The SentEmail an event is about, matched on identifiers only.

    Never on the recipient address alone: the Mailgun domain is shared with other
    apps, so events for mail that is not ours reach this endpoint too.
    """
    if event.sent_email_id is not None:
        found = SentEmail.objects.filter(id=event.sent_email_id).first()
        # Ids are per database: another environment on the same Mailgun domain
        # (dev and production) can send the same id for a different email, so the
        # recipient has to agree too.
        if found and (not event.recipient or normalize(found.company_email) == event.recipient):
            return found
    if event.message_id:
        return SentEmail.objects.filter(
            mailgun_message_id__in=[event.message_id, f"<{event.message_id}>"],
        ).first()
    return None


def status_for(event: ParsedEvent) -> tuple[str, str]:
    """(delivery_status, bounce_class) an event would set, before ordering rules."""
    if event.kind == "delivered":
        return SentEmail.DELIVERY_DELIVERED, ""
    if event.kind == "complained":
        return SentEmail.DELIVERY_COMPLAINED, ""
    return classify_failure(
        event.severity, event.reason, event.smtp_code, event.enhanced_code, event.detail,
    )


def apply_event(event: ParsedEvent, sent_email: SentEmail | None = None) -> str:
    """Record an event and update its SentEmail. Returns what happened:

    "applied", "duplicate" (already seen) or "unmatched" (not one of our emails).
    """
    sent_email = sent_email or find_sent_email(event)
    if sent_email is None:
        return "unmatched"

    try:
        with transaction.atomic():
            DeliveryEvent.objects.create(
                sent_email=sent_email,
                provider_event_id=event.event_id,
                kind=event.kind,
                severity=event.severity,
                smtp_code=event.smtp_code,
                enhanced_code=event.enhanced_code,
                reason=event.reason,
                detail=event.detail,
                recipient=event.recipient,
                occurred_at=event.occurred_at,
                raw=event.raw,
            )
    except IntegrityError:
        return "duplicate"

    with transaction.atomic():
        locked = SentEmail.objects.select_for_update().get(pk=sent_email.pk)
        incoming, bounce_class = status_for(event)
        new_status = next_status(locked.delivery_status, incoming)
        locked.delivery_status = new_status
        if new_status == incoming:
            # Only the event that decided the status explains it.
            locked.bounce_class = bounce_class
            locked.delivery_detail = event.detail or event.reason
        locked.delivery_updated_at = event.occurred_at
        locked.save(update_fields=[
            "delivery_status", "bounce_class", "delivery_detail", "delivery_updated_at",
        ])
    return "applied"


# --- Reports -----------------------------------------------------------------

# Latest conclusive result per address decides whether it is still dead: a later
# "delivered" (the mailbox was created, or the CRM address was fixed) clears it.
_CONCLUSIVE = (
    SentEmail.DELIVERY_DELIVERED,
    SentEmail.DELIVERY_BOUNCED,
    SentEmail.DELIVERY_SUPPRESSED,
    SentEmail.DELIVERY_COMPLAINED,
)
_DEAD_BOUNCES = (SentEmail.BOUNCE_MAILBOX_MISSING, SentEmail.BOUNCE_DOMAIN_MISSING)


def is_dead(status: str, bounce_class: str) -> bool:
    """True when sending to this address again is pointless or harmful."""
    if status == SentEmail.DELIVERY_BOUNCED:
        return bounce_class in _DEAD_BOUNCES
    return status in (SentEmail.DELIVERY_SUPPRESSED, SentEmail.DELIVERY_COMPLAINED)


def latest_results() -> dict[str, SentEmail]:
    """Most recent conclusive SentEmail per (normalized) recipient address."""
    rows = (
        SentEmail.objects.filter(success=True, delivery_status__in=_CONCLUSIVE)
        .order_by("sent_at", "id")
    )
    latest: dict[str, SentEmail] = {}
    for row in rows:
        latest[normalize(row.company_email)] = row
    return latest


def undeliverable_addresses() -> set[str]:
    """Addresses that must not be mailed: no mailbox/domain, refused, or complained."""
    return {
        address for address, row in latest_results().items()
        if is_dead(row.delivery_status, row.bounce_class)
    }


def problem_addresses(dead_only: bool = True) -> list[dict]:
    """One row per address whose latest conclusive result is a problem.

    dead_only=True keeps the addresses to fix in the CRM (see is_dead); False adds
    the ones that are only temporarily problematic (full mailbox, policy block,
    other permanent failure).
    """
    problem_statuses = (
        SentEmail.DELIVERY_BOUNCED, SentEmail.DELIVERY_SUPPRESSED, SentEmail.DELIVERY_COMPLAINED,
    )
    rows = []
    for address, row in latest_results().items():
        if dead_only:
            if not is_dead(row.delivery_status, row.bounce_class):
                continue
        elif row.delivery_status not in problem_statuses:
            continue
        attempts = SentEmail.objects.filter(
            success=True, company_email__iexact=address,
        ).count()
        rows.append({
            "address": address,
            "company_name": row.company_name,
            "twenty_crm_id": row.twenty_crm_id,
            "delivery_status": row.delivery_status,
            "bounce_class": row.bounce_class,
            "delivery_detail": row.delivery_detail,
            "last_event_at": row.delivery_updated_at,
            "emails_sent": attempts,
        })
    rows.sort(key=lambda r: (r["last_event_at"] is None, r["last_event_at"]), reverse=True)
    return rows
