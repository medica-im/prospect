"""Seed a development database with a believable year of sent-email history.

Dev never mails anyone (EMAIL_DRY_RUN), so without this there is no history to
develop or test the send page against. Rows are created for the real CRM
addresses, in campaign waves over the past year, and marked by their
mailgun_message_id prefix: a rerun replaces them, --clear removes them, and
genuine or dry-run sends are never touched.

    docker compose -f docker-compose-development.yml exec web python manage.py seed_sent_history
"""

import collections
import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from emails.models import CompanyType, EmailTemplate, SentEmail, Unsubscribe
from emails.services.renderer import build_context
from emails.services.twenty_crm import fetch_companies

SEED_PREFIX = "<dry-run.seed-"

# Which template each company type was prospected with. Other types get no history.
TEMPLATE_FOR_TYPE = {
    "CPTS": "cpts_prospect",
    "INTER_CPTS": "cpts_prospect",
    "MSP": "msp_prospect",
}

# Days ago of each campaign wave.
CAMPAIGN_DAYS = [380, 330, 290, 250, 210, 175, 140, 105, 75, 50, 28, 12]

# How many waves an address was part of: most few, a long tail of many.
COUNT_WEIGHTS = {0: 35, 1: 25, 2: 15, 3: 10, 4: 6, 5: 4, 7: 3, 10: 2}

# Share of sends that hit a transient Mailgun error and succeeded on retry.
RETRY_RATE = 0.04


class Command(BaseCommand):
    help = "Seed the dev database with fake sent-email history (dev only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true", help="only remove previously seeded rows"
        )
        parser.add_argument(
            "--seed", type=int, default=42, help="random seed, for a reproducible history"
        )

    def handle(self, *args, clear=False, seed=42, **options):
        # Fake sends look exactly like real ones on every page: never in production.
        if not (settings.DEBUG and settings.EMAIL_DRY_RUN):
            raise CommandError("seed_sent_history only runs with DEBUG and EMAIL_DRY_RUN on.")

        deleted, _ = SentEmail.objects.filter(mailgun_message_id__startswith=SEED_PREFIX).delete()
        if clear:
            self.stdout.write(f"Removed {deleted} seeded row(s).")
            return

        rows, per_address = self._build_rows(random.Random(seed))
        created = SentEmail.objects.bulk_create([se for se, _ in rows])
        # auto_now_add stamped them all "now"; put the intended dates back.
        for se, (_, when) in zip(created, rows):
            se.sent_at = when
        SentEmail.objects.bulk_update(created, ["sent_at"], batch_size=500)

        succeeded = sum(1 for se in created if se.success)
        self.stdout.write(
            f"Replaced {deleted} seeded row(s) with {len(created)}: "
            f"{succeeded} successful, {len(created) - succeeded} failed."
        )
        dist = collections.Counter(per_address.values())
        self.stdout.write(f"Addresses by emails received: {dict(sorted(dist.items()))}")

    def _build_rows(self, rng):
        now = timezone.now()
        types = {ct.name: ct for ct in CompanyType.objects.all()}
        templates = {t.name: t for t in EmailTemplate.objects.all()}
        unsubscribed = {
            u.email.strip().lower(): u.unsubscribed_at for u in Unsubscribe.objects.all()
        }
        campaigns = [
            (now - timedelta(days=d)).replace(hour=8, minute=30, second=0, microsecond=0)
            for d in CAMPAIGN_DAYS
        ]

        rows = []  # (unsaved SentEmail, sent_at)
        per_address = collections.Counter()
        for company in fetch_companies():
            template = templates.get(TEMPLATE_FOR_TYPE.get(company["company_type"], ""))
            ctype = types.get(company["company_type"])
            if not template or not ctype:
                continue

            for crm_id, email in self._recipients(company):
                n = rng.choices(list(COUNT_WEIGHTS), weights=list(COUNT_WEIGHTS.values()))[0]
                waves = campaigns
                unsub_at = unsubscribed.get(email.lower())
                if unsub_at:
                    # An opt-out must have received something, and nothing after.
                    waves = [c for c in campaigns if c < unsub_at] or [unsub_at - timedelta(days=3)]
                    n = max(1, min(n, len(waves)))
                if n == 0:
                    continue

                base = dict(
                    template=template,
                    company_name=company["name"],
                    company_email=email,
                    company_type=ctype,
                    twenty_crm_id=crm_id,
                )
                # A name the article table cannot handle fails at send time, every time.
                try:
                    build_context(company["name"], email)
                except Exception as exc:
                    when = rng.choice(waves[-3:]) + timedelta(seconds=rng.randint(0, 3600))
                    rows.append((self._row(base, success=False, error=str(exc)), when))
                    continue

                for wave in sorted(rng.sample(waves, min(n, len(waves)))):
                    when = wave + timedelta(seconds=rng.randint(0, 3600))
                    if rng.random() < RETRY_RATE:
                        # A transient Mailgun error, then the Celery retry 60 s later.
                        rows.append(
                            (self._row(base, success=False, error="503 Service Unavailable"), when)
                        )
                        when += timedelta(seconds=60)
                    rows.append((self._row(base, success=True), when))
                    per_address[email.lower()] += 1
        return rows, per_address

    @staticmethod
    def _recipients(company):
        """The addresses the send page offers: company ones, then people, each once."""
        seen = set()
        for crm_id, email in [(company["id"], e) for e in company["emails"]] + [
            (p["id"], p.get("email")) for p in company.get("people") or []
        ]:
            if email and email.lower() not in seen:
                seen.add(email.lower())
                yield crm_id, email

    @staticmethod
    def _row(base, success, error=""):
        # Failed rows carry the marker too, so --clear and reruns catch them.
        domain = settings.MAILGUN_DOMAIN or "dry-run.invalid"
        kind = "" if success else "failed-"
        return SentEmail(
            **base,
            success=success,
            error_message=error,
            mailgun_message_id=f"{SEED_PREFIX}{kind}{uuid.uuid4().hex}@{domain}>",
        )
