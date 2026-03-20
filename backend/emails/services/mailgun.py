import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str) -> dict:
    """Send an email via Mailgun API. Returns the Mailgun response dict."""
    response = httpx.post(
        settings.MAILGUN_API_URL,
        auth=(settings.MAILGUN_SENDING_KEY_ID, settings.MAILGUN_SENDING_KEY),
        data={
            "from": settings.MAILGUN_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html_body,
        },
    )
    if not response.is_success:
        logger.error(f"Mailgun error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()
