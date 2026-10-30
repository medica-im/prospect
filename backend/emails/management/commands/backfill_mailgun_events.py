"""Import what Mailgun already knows about emails sent before webhooks existed.

Two sources, both applied through the same code path as live webhooks:

* Suppression lists (/bounces, /complaints): every address Mailgun gave up on.
  No retention limit, so this is the authoritative source of past dead
  addresses. Entries carry no message id, so each is matched to the address's
  latest email sent before the bounce.
* Events API (/events): per-message delivered/failed/complained events, matched
  on the Message-ID. Mailgun keeps these only for a limited time (days to weeks
  depending on the plan), so it fills in recent history only.

Safe to re-run: every event has a unique id and is applied once.

    python manage.py backfill_mailgun_events --days 30
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from emails.models import SentEmail
from emails.services.delivery import ParsedEvent, apply_event, normalize_message_id, parse_event
from emails.services.mailgun_api import MailgunApiError, client, paginate
from emails.services.unsubscribe import normalize


class Command(BaseCommand):
    help = "Backfill delivery status of past emails from Mailgun (suppression lists + events)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="how far back to read events")
        parser.add_argument("--skip-lists", action="store_true", help="skip bounce/complaint lists")
        parser.add_argument("--skip-events", action="store_true", help="skip the Events API")

    def handle(self, *args, days=30, skip_lists=False, skip_events=False, **options):
        domain = settings.MAILGUN_DOMAIN
        counts = {"applied": 0, "duplicate": 0, "unmatched": 0, "inferred": 0}
        try:
            with client() as http:
                if not skip_lists:
                    for kind, path in (("bounce", "bounces"), ("complaint", "complaints")):
                        for item in paginate(http, f"/v3/{domain}/{path}", {"limit": 1000}):
                            self._tally(counts, self._apply_list_item(kind, item, counts))
                if not skip_events:
                    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
                    params = {
                        "event": "delivered OR failed OR complained",
                        "begin": since.timestamp(),
                        "ascending": "yes",
                        "limit": 300,
                    }
                    for item in paginate(http, f"/v3/{domain}/events", params):
                        event = parse_event(item)
                        if event is not None:
                            self._tally(counts, apply_event(event))
        except MailgunApiError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            f"Applied {counts['applied']}, already known {counts['duplicate']}, "
            f"not ours/unmatched {counts['unmatched']}, "
            f"inferred refused {counts['inferred']}."
        )

    @staticmethod
    def _tally(counts, result):
        counts[result] += 1

    def _apply_list_item(self, kind: str, item: dict, counts: dict) -> str:
        address = normalize(item.get("address", ""))
        try:
            created = parsedate_to_datetime(item["created_at"])
        except (KeyError, TypeError, ValueError):
            created = datetime.now(tz=timezone.utc)

        # Independent of whether the entry itself matches one of our emails: we may
        # only have mailed the address after another app got it listed.
        counts["inferred"] += self._infer_refused(kind, address, created)

        # The list holds only the address, so find our latest email to it that the
        # bounce can be about. Never an email sent after the bounce was recorded.
        sent_email = (
            SentEmail.objects.filter(
                success=True, company_email__iexact=address, sent_at__lte=created,
            )
            .order_by("-sent_at")
            .first()
        )
        if sent_email is None:
            return "unmatched"

        if kind == "complaint":
            event = ParsedEvent(
                event_id=f"complaint-list:{address}:{created.isoformat()}",
                kind="complained", recipient=address, occurred_at=created, raw=item,
            )
        else:
            code = str(item.get("code") or "")
            error = str(item.get("error") or "")
            event = parse_event({
                "id": f"bounce-list:{address}:{created.isoformat()}",
                "event": "failed",
                "severity": "permanent",
                "recipient": address,
                "timestamp": created.timestamp(),
                "delivery-status": {"code": code, "message": error},
            })
        event.message_id = normalize_message_id(sent_email.mailgun_message_id)
        return apply_event(event, sent_email=sent_email)

    @staticmethod
    def _infer_refused(kind: str, address: str, listed_at: datetime) -> int:
        """Mark our later emails to a listed address as refused. Returns how many.

        Mailgun stops delivering to an address once it is on its bounce or
        complaint list, so every email sent after that date was refused. The
        Events API only remembers about 30 days, so for older ones nothing says
        so and they would stay "sent" and keep counting as received. Only emails
        with no outcome yet are touched: an observed status is never overridden.
        The event id is per email, so re-runs change nothing.
        """
        reason = "suppress-complaint" if kind == "complaint" else "suppress-bounce"
        detail = (
            f"Déduit : adresse sur la liste d'exclusion Mailgun "
            f"({'plainte' if kind == 'complaint' else 'rebond'}) depuis le {listed_at:%Y-%m-%d}"
        )
        later = SentEmail.objects.filter(
            success=True,
            company_email__iexact=address,
            sent_at__gt=listed_at,
            delivery_status=SentEmail.DELIVERY_SENT,
        )
        inferred = 0
        for sent_email in later:
            event = parse_event({
                "id": f"list-refused:{address}:{sent_email.id}",
                "event": "failed",
                "severity": "permanent",
                "reason": reason,
                "recipient": address,
                "timestamp": sent_email.sent_at.timestamp(),
                "delivery-status": {"message": detail},
            })
            if apply_event(event, sent_email=sent_email) == "applied":
                inferred += 1
        return inferred
