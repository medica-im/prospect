"""Mailgun's bounce and complaint lists, kept as data (models.MailgunSuppression).

The /bounces list gives, per address, the SMTP `code`, the `error` message and
`created_at` (RFC 822). /complaints gives the address and the date only.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..models import MailgunSuppression
from .delivery import bounce_detail, classify_failure, extract_enhanced_code
from .unsubscribe import normalize


def parse_listed_at(item: dict) -> datetime:
    try:
        return parsedate_to_datetime(item["created_at"])
    except (KeyError, TypeError, ValueError):
        return datetime.now(tz=timezone.utc)


def record_list_item(kind: str, item: dict) -> MailgunSuppression:
    """Create or refresh the row for one item of Mailgun's bounce or complaint list."""
    code = str(item.get("code") or "")
    error = str(item.get("error") or "")
    enhanced, bounce_class = "", ""
    if kind == MailgunSuppression.KIND_BOUNCE:
        enhanced = extract_enhanced_code(error)
        _status, bounce_class = classify_failure(
            "permanent", "", code, enhanced, bounce_detail(code, error),
        )
    row, _created = MailgunSuppression.objects.update_or_create(
        address=normalize(item.get("address", "")),
        kind=kind,
        defaults={
            "code": code, "error": error, "enhanced_code": enhanced,
            "bounce_class": bounce_class, "listed_at": parse_listed_at(item),
        },
    )
    return row
