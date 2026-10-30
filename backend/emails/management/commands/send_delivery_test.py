"""Send a REAL email through Mailgun to an address we control, to watch the
delivery webhook update its status end to end (dev only).

Dev normally never mails anyone (EMAIL_DRY_RUN). This is the one deliberate
exception, and it can only reach SAFE_DOMAIN: every recipient is checked, and
anything else is refused before Mailgun is called. Aim it at an address that
does not exist (the default) to produce a genuine "mailbox does not exist"
bounce, or at a real mailbox to see a "delivered".

    python manage.py send_delivery_test                 # a random, non-existent mailbox
    python manage.py send_delivery_test you@medica.im   # an existing one
    python manage.py send_delivery_test --clear         # remove the test rows

Whether a bounce comes back depends on the medica.im mail server rejecting
unknown recipients; a catch-all mailbox would accept everything.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from emails.models import SentEmail
from emails.services.mailgun import send_email

SAFE_DOMAIN = "medica.im"
TEST_CRM_ID = "delivery-test"
TEST_COMPANY = "[delivery test]"


def is_safe_recipient(address: str) -> bool:
    """True only for a plain local@medica.im address (no lookalike domains).

    Django's validator does the syntax (one "@", no commas or display names);
    the domain must then match exactly, and quoted local parts are refused
    because they can hide a second address inside the quotes.
    """
    try:
        validate_email(address)
    except ValidationError:
        return False
    local, _, domain = address.rpartition("@")
    return domain.lower() == SAFE_DOMAIN and not local.startswith('"')


class Command(BaseCommand):
    help = f"Send a real test email to @{SAFE_DOMAIN} addresses to exercise delivery webhooks (dev only)."

    def add_arguments(self, parser):
        parser.add_argument("addresses", nargs="*", help=f"recipients, only @{SAFE_DOMAIN} (default: one random non-existent mailbox)")
        parser.add_argument("--clear", action="store_true", help="only remove earlier test rows")

    def handle(self, *args, addresses=(), clear=False, **options):
        if not settings.DEBUG:
            raise CommandError("send_delivery_test only runs with DEBUG on (dev).")

        if clear:
            deleted, _ = SentEmail.objects.filter(twenty_crm_id=TEST_CRM_ID).delete()
            self.stdout.write(f"Removed {deleted} test row(s).")
            return

        addresses = list(addresses) or [f"delivery-test-{uuid.uuid4().hex[:10]}@{SAFE_DOMAIN}"]
        refused = [a for a in addresses if not is_safe_recipient(a)]
        if refused:
            raise CommandError(f"Refusing: only plain @{SAFE_DOMAIN} addresses are allowed, got {refused}.")
        if not (settings.MAILGUN_API_URL and settings.MAILGUN_SENDING_KEY):
            raise CommandError("MAILGUN_API_URL and MAILGUN_SENDING_KEY must be set.")

        for address in addresses:
            sent = SentEmail.objects.create(
                company_name=TEST_COMPANY, company_email=address, twenty_crm_id=TEST_CRM_ID,
                success=False,
            )
            try:
                result = send_email(
                    to=address,
                    subject="Test de distribution (prospect, dev)",
                    html_body="<p>Message de test automatique, sans action requise.</p>",
                    sent_email_id=sent.id,
                    dry_run=False,
                )
            except Exception as exc:
                sent.error_message = str(exc)
                sent.save(update_fields=["error_message"])
                raise CommandError(f"Mailgun refused the send to {address}: {exc}")
            sent.success = True
            sent.mailgun_message_id = result.get("id", "")
            sent.save(update_fields=["success", "mailgun_message_id"])
            self.stdout.write(
                f"Sent to {address} (sent email #{sent.id}). "
                f"Watch /emails/sent/{sent.id}: the status changes when Mailgun calls the webhook."
            )
