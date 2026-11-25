"""Re-run the bounce classifier over bounces stored before it knew a pattern.

classify_failure() is applied once, when Mailgun reports a bounce, so a pattern
it learns later (5.7.13 "Disabled recipient address", Exchange 5.4.1 "Access
denied", ...) does not reach the rows already stored. Those rows matter: only a
"mailbox_missing" or "domain_missing" bounce stops the address from being offered
and mailed again. Reports what would change; --apply writes it.

    python manage.py reclassify_bounces            # report only
    python manage.py reclassify_bounces --apply
"""

import collections

from django.core.management.base import BaseCommand

from emails.models import MailgunSuppression, SentEmail
from emails.services.delivery import bounce_detail, classify_failure, extract_enhanced_code


def _new_class(detail: str) -> str:
    return classify_failure("permanent", "", "", extract_enhanced_code(detail), detail)[1]


class Command(BaseCommand):
    help = "Recompute bounce_class of stored bounces with the current classifier."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")

    def handle(self, *args, apply=False, **options):
        changes = collections.Counter()

        for row in SentEmail.objects.filter(delivery_status=SentEmail.DELIVERY_BOUNCED):
            new = _new_class(row.delivery_detail)
            if new != row.bounce_class:
                changes[("sent email", row.bounce_class, new)] += 1
                if apply:
                    SentEmail.objects.filter(pk=row.pk).update(bounce_class=new)

        for row in MailgunSuppression.objects.filter(kind=MailgunSuppression.KIND_BOUNCE):
            new = _new_class(bounce_detail(row.code, row.error))
            if new != row.bounce_class:
                changes[("mailgun list", row.bounce_class, new)] += 1
                if apply:
                    MailgunSuppression.objects.filter(pk=row.pk).update(bounce_class=new)

        for (where, old, new), count in sorted(changes.items()):
            self.stdout.write(f"{where}: {old or '-'} -> {new}: {count}")
        verb = "Changed" if apply else "Would change"
        self.stdout.write(f"{verb} {sum(changes.values())} row(s)." + ("" if apply else " Run with --apply."))
