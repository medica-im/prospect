import logging

from ..tasks import send_prospect_email
from .unsubscribe import filter_recipients

logger = logging.getLogger(__name__)


def dispatch_batch(template, recipients) -> tuple[int, list]:
    """Queue one send task per allowed recipient. Returns (queued, blocked).

    Shared by the immediate send and the scheduled batches. Unsubscribed and
    undeliverable recipients are dropped here so the operator gets feedback; the
    task re-checks before sending, which is the real gate.
    """
    allowed, blocked = filter_recipients(recipients)

    for recipient in allowed:
        send_prospect_email.delay(
            template_id=template.id,
            company_name=recipient.company_name,
            company_email=recipient.company_email,
            company_type_id=recipient.company_type_id,
            twenty_crm_id=recipient.twenty_crm_id,
        )

    if blocked:
        logger.info(f"Skipped {len(blocked)} unsubscribed or undeliverable recipient(s)")
    return len(allowed), blocked
