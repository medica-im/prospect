"""Point Mailgun's delivery webhooks at this app, keeping any URL already there.

The Mailgun domain can be shared with another app (clinic-cms), and a webhook
event type accepts several URLs. This command only ever ADDS our URL; it never
removes or replaces another one. (clinic-cms's own register command replaces a
single URL when run with --replace — do not use that on a shared domain.)

    python manage.py register_mail_webhooks --dry-run
    python manage.py register_mail_webhooks
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from emails.services.mailgun_api import MAX_WEBHOOK_URLS, MailgunApiError, client

EVENTS = ("delivered", "permanent_fail", "temporary_fail", "complained")


class Command(BaseCommand):
    help = "Add this app's Mailgun delivery webhook URL, leaving other URLs in place."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="show what would change")
        parser.add_argument(
            "--url",
            default=f"{settings.SITE_URL.rstrip('/')}/api/webhooks/mailgun",
            help="webhook URL (default: SITE_URL + /api/webhooks/mailgun)",
        )

    def handle(self, *args, dry_run=False, url="", **options):
        domain = settings.MAILGUN_DOMAIN
        try:
            with client() as http:
                current = http.get(f"/v3/domains/{domain}/webhooks")
                if current.status_code >= 400:
                    raise MailgunApiError(
                        f"Listing webhooks failed ({current.status_code}): {current.text[:300]}"
                    )
                registered = current.json().get("webhooks", {})

                for event in EVENTS:
                    urls = self._urls(registered.get(event))
                    if url in urls:
                        self.stdout.write(f"{event}: already registered ({len(urls)} URL(s)).")
                        continue
                    if len(urls) >= MAX_WEBHOOK_URLS:
                        raise CommandError(
                            f"{event} already has {len(urls)} URLs; remove one in Mailgun first."
                        )
                    wanted = urls + [url]
                    others = f", next to {len(urls)} other URL(s)" if urls else ""
                    self.stdout.write(f"{event}: adding {url}{others}.")
                    if dry_run:
                        continue
                    # PUT replaces the whole list for the event, so send existing + ours.
                    method = http.put if urls else http.post
                    response = method(
                        f"/v3/domains/{domain}/webhooks" + (f"/{event}" if urls else ""),
                        data={"id": event, "url": wanted} if not urls else {"url": wanted},
                    )
                    if response.status_code >= 400:
                        raise MailgunApiError(
                            f"Registering {event} failed ({response.status_code}): {response.text[:300]}"
                        )
        except MailgunApiError as exc:
            raise CommandError(str(exc))

        if dry_run:
            self.stdout.write("Dry run: nothing changed.")

    @staticmethod
    def _urls(entry) -> list[str]:
        """URLs of a webhook entry. Mailgun returns `urls` (list) or, older, `url`."""
        if not entry:
            return []
        if entry.get("urls"):
            return list(entry["urls"])
        return [entry["url"]] if entry.get("url") else []
