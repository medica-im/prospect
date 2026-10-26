import logging
import uuid

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    unsubscribe_url: str | None = None,
) -> dict:
    """Send an email via Mailgun API. Returns the Mailgun response dict.

    When unsubscribe_url is given, the List-Unsubscribe headers are set so mail
    clients show their native unsubscribe control. Gmail and Yahoo require this
    of bulk senders, and it steers opt-outs away from the spam button.
    """
    if settings.EMAIL_DRY_RUN:
        # Shaped like Mailgun's reply; the prefix keeps these ids recognisable.
        domain = settings.MAILGUN_DOMAIN or "dry-run.invalid"
        logger.info(f"Dry run: not sending '{subject}' to {to}")
        return {"id": f"<dry-run.{uuid.uuid4().hex}@{domain}>", "message": "Dry run, not sent."}

    data = {
        "from": settings.MAILGUN_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }

    if unsubscribe_url:
        data["h:List-Unsubscribe"] = f"<{unsubscribe_url}>"
        data["h:List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    response = httpx.post(
        settings.MAILGUN_API_URL,
        auth=(settings.MAILGUN_SENDING_KEY_ID, settings.MAILGUN_SENDING_KEY),
        data=data,
    )
    if not response.is_success:
        logger.error(f"Mailgun error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()
