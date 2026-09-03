"""Unsubscribe tokens and the suppression list.

Tokens are stateless: `django.core.signing` signs {email, sent_email_id} with a
dedicated salt, so an unsubscribe link needs no database column and can be built
before the SentEmail row is even saved. Tokens never expire — an unsubscribe link
must keep working however old the email is.
"""

import logging

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

SALT = "emails.unsubscribe"


def normalize(email: str) -> str:
    """Addresses are compared case-insensitively and without surrounding space."""
    return (email or "").strip().lower()


def make_token(email: str, sent_email_id: int | None = None) -> str:
    """Sign an unsubscribe payload. `se` is the SentEmail that carried the link."""
    return signing.dumps({"e": normalize(email), "se": sent_email_id}, salt=SALT)


def load_token(token: str) -> dict:
    """Verify a token and return {"email": str, "sent_email_id": int | None}.

    Raises django.core.signing.BadSignature on a tampered or malformed token.
    No max_age: unsubscribe links do not expire.
    """
    data = signing.loads(token, salt=SALT)
    if not isinstance(data, dict) or not data.get("e"):
        raise signing.BadSignature("Malformed unsubscribe payload")
    return {"email": normalize(data["e"]), "sent_email_id": data.get("se")}


def build_unsubscribe_url(email: str, sent_email_id: int | None = None) -> str:
    """Absolute URL of the unsubscribe confirmation page for this recipient.

    Signed tokens are already URL-safe (base64url segments joined by ":"), so
    they are embedded verbatim — percent-encoding the ":" would only make the
    link uglier and harder to copy out of a mail client.
    """
    base = settings.SITE_URL.rstrip("/")
    return f"{base}/api/unsubscribe/{make_token(email, sent_email_id)}"


def is_unsubscribed(email: str) -> bool:
    from ..models import Unsubscribe

    return Unsubscribe.objects.filter(email=normalize(email)).exists()


def suppressed_emails() -> set[str]:
    """Every normalized address on the suppression list."""
    from ..models import Unsubscribe

    return set(Unsubscribe.objects.values_list("email", flat=True))


def filter_recipients(recipients: list) -> tuple[list, list]:
    """Split recipients into (allowed, blocked) on their `company_email`.

    Accepts anything with a `company_email` attribute (SendEmailRecipient schemas).
    """
    suppressed = suppressed_emails()
    allowed, blocked = [], []
    for recipient in recipients:
        if normalize(recipient.company_email) in suppressed:
            blocked.append(recipient)
        else:
            allowed.append(recipient)
    return allowed, blocked
