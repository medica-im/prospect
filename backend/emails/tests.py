from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .models import CompanyType, EmailTemplate, SentEmail, Unsubscribe
from .services.mailgun import send_email
from .services.renderer import ensure_unsubscribe_link
from .services.unsubscribe import (
    build_unsubscribe_url,
    filter_recipients,
    is_unsubscribed,
    load_token,
    make_token,
)
from .tasks import send_prospect_email


class Recipient:
    """Stand-in for the SendEmailRecipient schema (only company_email is read)."""

    def __init__(self, company_email):
        self.company_email = company_email


class UnsubscribeTokenTests(TestCase):
    def test_token_roundtrip(self):
        token = make_token("Contact@Example.FR", 42)
        data = load_token(token)
        self.assertEqual(data["email"], "contact@example.fr")
        self.assertEqual(data["sent_email_id"], 42)

    def test_token_without_sent_email(self):
        self.assertIsNone(load_token(make_token("a@b.fr"))["sent_email_id"])

    def test_tampered_token_is_rejected(self):
        token = make_token("a@b.fr", 1)
        with self.assertRaises(signing.BadSignature):
            load_token(token[:-3] + "xxx")

    def test_garbage_token_is_rejected(self):
        with self.assertRaises(signing.BadSignature):
            load_token("not-a-token")

    def test_url_is_absolute_and_routed_under_api(self):
        with self.settings(SITE_URL="https://prospect.example.com/"):
            url = build_unsubscribe_url("a@b.fr", 7)
        self.assertTrue(url.startswith("https://prospect.example.com/api/unsubscribe/"))


class SuppressionListTests(TestCase):
    def setUp(self):
        Unsubscribe.objects.create(email="gone@example.fr")

    def test_is_unsubscribed_is_case_insensitive(self):
        self.assertTrue(is_unsubscribed("GONE@example.FR"))
        self.assertTrue(is_unsubscribed("  gone@example.fr "))
        self.assertFalse(is_unsubscribed("still@example.fr"))

    def test_filter_recipients_splits_allowed_and_blocked(self):
        allowed, blocked = filter_recipients(
            [Recipient("Gone@Example.fr"), Recipient("ok@example.fr")]
        )
        self.assertEqual([r.company_email for r in allowed], ["ok@example.fr"])
        self.assertEqual([r.company_email for r in blocked], ["Gone@Example.fr"])


class UnsubscribeFooterTests(TestCase):
    def test_footer_appended_when_link_missing(self):
        html = ensure_unsubscribe_link("<html><body><p>Bonjour</p></body></html>", "https://x/u/1")
        self.assertIn("https://x/u/1", html)
        self.assertIn("Se désabonner", html)
        self.assertTrue(html.rstrip().endswith("</body></html>"))

    def test_footer_not_duplicated_when_link_present(self):
        html = ensure_unsubscribe_link(
            '<html><body><a href="https://x/u/1">stop</a></body></html>', "https://x/u/1"
        )
        self.assertEqual(html.count("https://x/u/1"), 1)

    def test_appended_when_no_body_tag(self):
        self.assertIn("https://x/u/1", ensure_unsubscribe_link("<p>Bonjour</p>", "https://x/u/1"))


class UnsubscribeViewTests(TestCase):
    def setUp(self):
        self.company_type = CompanyType.objects.create(name="msp", label="MSP")
        self.template = EmailTemplate.objects.create(
            name="T", subject_template="S", html_body="<html><body>B</body></html>"
        )
        self.sent = SentEmail.objects.create(
            template=self.template,
            company_name="MSP du Marais",
            company_email="contact@marais.fr",
            company_type=self.company_type,
            twenty_crm_id="crm-1",
            success=True,
        )
        self.token = make_token("contact@marais.fr", self.sent.id)
        self.url = f"/api/unsubscribe/{self.token}"

    def test_get_shows_confirmation_without_unsubscribing(self):
        """Mail scanners prefetch links — a GET must never opt anyone out."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Se désabonner")
        self.assertEqual(Unsubscribe.objects.count(), 0)

    def test_post_records_the_unsubscribe(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "medecinelibre.com")

        record = Unsubscribe.objects.get()
        self.assertEqual(record.email, "contact@marais.fr")
        self.assertEqual(record.sent_email, self.sent)
        self.assertEqual(record.company_name, "MSP du Marais")
        self.assertEqual(record.twenty_crm_id, "crm-1")
        self.assertEqual(record.source, Unsubscribe.SOURCE_LINK)

    def test_post_is_idempotent(self):
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(Unsubscribe.objects.count(), 1)

    def test_one_click_post_is_flagged_as_list_header(self):
        self.client.post(self.url, {"List-Unsubscribe": "One-Click"})
        self.assertEqual(Unsubscribe.objects.get().source, Unsubscribe.SOURCE_LIST_HEADER)

    def test_invalid_token_renders_page_without_recording(self):
        response = self.client.post("/api/unsubscribe/garbage")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "n'est pas valide")
        self.assertEqual(Unsubscribe.objects.count(), 0)

    def test_client_ip_taken_from_forwarded_header(self):
        self.client.post(self.url, HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1")
        self.assertEqual(Unsubscribe.objects.get().ip_address, "203.0.113.9")

    def test_get_reports_already_unsubscribed(self):
        Unsubscribe.objects.create(email="contact@marais.fr")
        self.assertContains(self.client.get(self.url), "déjà désabonné")


class SendFilteringTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        self.company_type = CompanyType.objects.create(name="msp", label="MSP")
        self.template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<html><body>B</body></html>"
        )
        Unsubscribe.objects.create(email="gone@example.fr")

    def _payload(self, *emails):
        return {
            "template_id": self.template.id,
            "recipients": [
                {
                    "company_name": "MSP du Marais",
                    "company_email": email,
                    "company_type_id": self.company_type.id,
                    "twenty_crm_id": "crm-1",
                }
                for email in emails
            ],
        }

    @patch("emails.api.send_prospect_email")
    def test_api_skips_unsubscribed_recipients(self, mock_task):
        response = self.client.post(
            "/api/emails/send",
            data=self._payload("ok@example.fr", "gone@example.fr"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["queued"], 1)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(body["skipped_emails"], ["gone@example.fr"])
        self.assertEqual(mock_task.delay.call_count, 1)
        self.assertEqual(
            mock_task.delay.call_args.kwargs["company_email"], "ok@example.fr"
        )

    @patch("emails.tasks.send_email")
    def test_task_refuses_unsubscribed_recipient(self, mock_send):
        """The task is the real gate: a task queued before an opt-out still runs."""
        result = send_prospect_email(
            template_id=self.template.id,
            company_name="MSP du Marais",
            company_email="gone@example.fr",
            company_type_id=self.company_type.id,
            twenty_crm_id="crm-1",
        )
        self.assertEqual(result["status"], "skipped")
        mock_send.assert_not_called()
        self.assertEqual(SentEmail.objects.count(), 0)

    @patch("emails.tasks.save_to_sent_folder")
    @patch("emails.tasks.send_email")
    def test_send_passes_unsubscribe_url_to_mailgun_and_body(self, mock_send, _imap):
        mock_send.return_value = {"id": "<mg-1>"}
        with patch("emails.tasks.build_context") as mock_context:
            mock_context.side_effect = lambda name, email, url: {
                "company_name": name, "email": email,
                "definite_article_company_name": name, "unsubscribe_url": url,
            }
            send_prospect_email(
                template_id=self.template.id,
                company_name="MSP du Marais",
                company_email="ok@example.fr",
                company_type_id=self.company_type.id,
                twenty_crm_id="crm-1",
            )

        sent = SentEmail.objects.get()
        self.assertTrue(sent.success)
        url = mock_send.call_args.kwargs["unsubscribe_url"]
        self.assertIn("/api/unsubscribe/", url)
        # The token resolves back to this recipient and this very SentEmail.
        token = url.rsplit("/", 1)[1]
        self.assertEqual(load_token(token), {"email": "ok@example.fr", "sent_email_id": sent.id})
        # The footer fallback injected the link even though the template lacks it.
        self.assertIn(url, mock_send.call_args.kwargs["html_body"])


class EmailStatsByAddressTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        for email, success in [
            ("Contact@MSP.example", True),
            ("contact@msp.example", True),
            ("contact@msp.example", False),
            ("other@msp.example", True),
        ]:
            SentEmail.objects.create(
                company_name="MSP", company_email=email, twenty_crm_id="crm-1", success=success
            )

    def test_counts_successful_sends_per_lowercased_address(self):
        response = self.client.get("/api/email-stats/by-address")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            {address: s["total_sent"] for address, s in body.items()},
            {"contact@msp.example": 2, "other@msp.example": 1},
        )
        last_success = SentEmail.objects.filter(
            company_email__iexact="contact@msp.example", success=True
        ).latest("sent_at")
        self.assertEqual(
            body["contact@msp.example"]["last_sent_at"][:19],
            last_success.sent_at.isoformat()[:19],
        )


class DryRunTests(TestCase):
    def setUp(self):
        self.company_type = CompanyType.objects.create(name="msp", label="MSP")
        self.template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<html><body>B</body></html>"
        )

    @override_settings(EMAIL_DRY_RUN=True)
    @patch("emails.services.imap.MailBox")
    @patch("emails.services.mailgun.httpx.post")
    def test_dry_run_records_a_success_without_mailgun_or_imap(self, mock_post, mock_mailbox):
        with patch("emails.tasks.build_context") as mock_context:
            mock_context.side_effect = lambda name, email, url: {
                "company_name": name, "email": email,
                "definite_article_company_name": name, "unsubscribe_url": url,
            }
            result = send_prospect_email(
                template_id=self.template.id,
                company_name="MSP Exemple",
                company_email="ok@msp.example",
                company_type_id=self.company_type.id,
                twenty_crm_id="crm-1",
            )

        self.assertEqual(result["status"], "sent")
        sent = SentEmail.objects.get()
        self.assertTrue(sent.success)
        self.assertTrue(sent.mailgun_message_id.startswith("<dry-run."))
        mock_post.assert_not_called()
        mock_mailbox.assert_not_called()

    @override_settings(EMAIL_DRY_RUN=False, MAILGUN_API_URL="https://mailgun.invalid/messages")
    @patch("emails.services.mailgun.httpx.post")
    def test_live_mode_calls_mailgun(self, mock_post):
        mock_post.return_value.is_success = True
        mock_post.return_value.json.return_value = {"id": "<mg-1>"}
        self.assertEqual(send_email("ok@msp.example", "S", "<p>B</p>")["id"], "<mg-1>")
        mock_post.assert_called_once()


@patch("emails.management.commands.seed_sent_history.build_context")
@patch("emails.management.commands.seed_sent_history.fetch_companies")
class SeedSentHistoryTests(TestCase):
    COMPANIES = [
        {
            "id": "c1", "name": "CPTS Exemple", "company_type": "CPTS",
            "emails": ["contact@cpts.example", "Contact@CPTS.example"],
            "people": [{"id": "p1", "email": "alice@cpts.example"}, {"id": "p2", "email": ""}],
        },
        {"id": "c2", "name": "Cabinet", "company_type": "ORG_PRO", "emails": ["a@org.example"]},
    ]

    def setUp(self):
        cpts = CompanyType.objects.create(name="CPTS", label="CPTS")
        CompanyType.objects.create(name="ORG_PRO", label="Org")
        template = EmailTemplate.objects.create(
            name="cpts_prospect", subject_template="S", html_body="<p>B</p>"
        )
        template.company_types.add(cpts)
        self.real = SentEmail.objects.create(
            company_name="Real", company_email="real@x.example", twenty_crm_id="r", success=True,
            mailgun_message_id="<real@mailgun>",
        )

    def seed(self, *args):
        call_command("seed_sent_history", *args, stdout=StringIO())

    def seeded(self):
        return SentEmail.objects.filter(mailgun_message_id__startswith="<dry-run.seed-")

    @override_settings(DEBUG=True, EMAIL_DRY_RUN=True)
    def test_seeds_backdated_history_for_prospected_types_only(self, mock_fetch, _ctx):
        mock_fetch.return_value = self.COMPANIES
        # Enough seeds that both addresses get history in at least one.
        for seed in range(5):
            self.seed("--seed", str(seed))
            if self.seeded().filter(success=True).values("company_email").distinct().count() == 2:
                break
        rows = self.seeded()
        self.assertTrue(rows.exists())
        self.assertEqual(
            set(rows.values_list("company_email", flat=True)), {"contact@cpts.example", "alice@cpts.example"}
        )  # no ORG_PRO (no template), no duplicate-case address, no empty one
        self.assertTrue(all(r.sent_at < r.sent_at.now(r.sent_at.tzinfo) for r in rows))
        self.assertEqual(
            set(rows.filter(company_email="alice@cpts.example").values_list("twenty_crm_id", flat=True)),
            {"p1"},
        )

    @override_settings(DEBUG=True, EMAIL_DRY_RUN=True)
    def test_rerun_replaces_and_clear_removes_only_seeded_rows(self, mock_fetch, _ctx):
        mock_fetch.return_value = self.COMPANIES
        self.seed()
        first = self.seeded().count()
        self.seed()
        self.assertEqual(self.seeded().count(), first)  # same seed, replaced not added
        self.seed("--clear")
        self.assertFalse(self.seeded().exists())
        self.assertTrue(SentEmail.objects.filter(pk=self.real.pk).exists())

    @override_settings(DEBUG=True, EMAIL_DRY_RUN=True)
    def test_printed_distribution_matches_what_the_stats_count(self, mock_fetch, _ctx):
        """Seeded bounces must not count in the seed's own summary either."""
        import ast
        import collections

        from django.db.models.functions import Lower

        from .api import _reached

        mock_fetch.return_value = self.COMPANIES
        for seed in range(6):
            out = StringIO()
            call_command("seed_sent_history", "--seed", str(seed), stdout=out)
            printed = ast.literal_eval(out.getvalue().split("received:")[1].strip())
            per_address = collections.Counter(
                _reached().filter(mailgun_message_id__startswith="<dry-run.seed-")
                .annotate(a=Lower("company_email")).values_list("a", flat=True)
            )
            self.assertEqual(printed, dict(collections.Counter(per_address.values())), f"seed {seed}")

    @override_settings(DEBUG=False, EMAIL_DRY_RUN=False)
    def test_refuses_outside_dev(self, mock_fetch, _ctx):
        with self.assertRaises(CommandError):
            self.seed()
        mock_fetch.assert_not_called()


# --- Delivery reports --------------------------------------------------------

import hashlib
import hmac
import json
import time

from .models import DeliveryEvent
from .services.delivery import (
    classify_failure,
    next_status,
    parse_event,
    undeliverable_addresses,
    verify_signature,
)

SIGNING_KEY = "test-signing-key"


def signed(event_data, key=SIGNING_KEY, timestamp=None):
    """A webhook body signed the way Mailgun signs it."""
    timestamp = str(int(timestamp if timestamp is not None else time.time()))
    token = "tok-" + timestamp
    digest = hmac.new(key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256).hexdigest()
    return {
        "signature": {"timestamp": timestamp, "token": token, "signature": digest},
        "event-data": event_data,
    }


def bounce_event(sent_email, code="550", message="5.1.1 <x@y.example>: Recipient address rejected: User unknown", **extra):
    return {
        "id": f"evt-{sent_email.id}-{code}",
        "event": "failed",
        "severity": "permanent",
        "recipient": sent_email.company_email,
        "timestamp": time.time(),
        "user-variables": {"sent_email_id": str(sent_email.id)},
        "message": {"headers": {"message-id": "mg-1@mail.example"}},
        "delivery-status": {"code": int(code), "message": message},
        **extra,
    }


class ClassifyFailureTests(TestCase):
    def classify(self, severity="permanent", reason="", code="550", enhanced="", detail=""):
        return classify_failure(severity, reason, code, enhanced, detail)

    def test_missing_mailbox(self):
        for enhanced, detail in [
            ("5.1.1", "550 5.1.1 The email account that you tried to reach does not exist"),
            ("5.1.10", "550 5.1.10 RESOLVER.ADR.RecipientNotFound; Recipient not found"),
            ("", "550 User unknown in virtual mailbox table"),
        ]:
            with self.subTest(detail=detail):
                self.assertEqual(
                    self.classify(enhanced=enhanced, detail=detail),
                    (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING),
                )

    def test_other_permanent_failures_are_told_apart(self):
        self.assertEqual(
            self.classify(enhanced="5.1.2", detail="550 5.1.2 Host not found"),
            (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_DOMAIN_MISSING),
        )
        self.assertEqual(
            self.classify(code="552", enhanced="5.2.2", detail="552 5.2.2 mailbox full"),
            (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_FULL),
        )
        self.assertEqual(
            self.classify(enhanced="5.7.1", detail="550 5.7.1 rejected"),
            (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_BLOCKED),
        )
        self.assertEqual(
            self.classify(detail="554 transaction failed"),
            (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_OTHER),
        )

    def test_temporary_and_suppressed(self):
        self.assertEqual(
            self.classify(severity="temporary", code="451", enhanced="4.7.1"),
            (SentEmail.DELIVERY_DEFERRED, ""),
        )
        self.assertEqual(
            self.classify(reason="suppress-bounce"), (SentEmail.DELIVERY_SUPPRESSED, "")
        )

    def test_explicit_code_beats_keywords(self):
        # "policy" would say blocked, but 5.1.1 is an unambiguous missing mailbox.
        self.assertEqual(
            self.classify(enhanced="5.1.1", detail="550 5.1.1 no such user, see our policy"),
            (SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING),
        )

    def test_status_ordering(self):
        self.assertEqual(next_status("bounced", "delivered"), "bounced")
        self.assertEqual(next_status("delivered", "deferred"), "delivered")
        self.assertEqual(next_status("bounced", "complained"), "complained")
        self.assertEqual(next_status("sent", "deferred"), "deferred")
        self.assertEqual(next_status("deferred", "delivered"), "delivered")


@override_settings(MAILGUN_WEBHOOK_SIGNING_KEY=SIGNING_KEY)
class SignatureTests(TestCase):
    def test_accepts_a_correct_signature(self):
        self.assertTrue(verify_signature(signed({})))

    def test_rejects_wrong_key_stale_and_malformed(self):
        self.assertFalse(verify_signature(signed({}, key="other")))
        self.assertFalse(verify_signature(signed({}, timestamp=time.time() - 24 * 3600)))
        self.assertFalse(verify_signature({"signature": {"timestamp": "x"}}))
        self.assertFalse(verify_signature({}))

    @override_settings(MAILGUN_WEBHOOK_SIGNING_KEY="")
    def test_unconfigured_key_rejects_everything(self):
        self.assertFalse(verify_signature(signed({}, key="")))


@override_settings(MAILGUN_WEBHOOK_SIGNING_KEY=SIGNING_KEY)
class MailgunWebhookTests(TestCase):
    url = "/api/webhooks/mailgun"

    def setUp(self):
        self.sent = SentEmail.objects.create(
            company_name="MSP", company_email="Dead@msp.example", twenty_crm_id="crm-9",
            success=True, mailgun_message_id="<mg-1@mail.example>",
        )

    def post(self, body):
        return self.client.post(self.url, data=json.dumps(body), content_type="application/json")

    def test_a_missing_mailbox_bounce_is_recorded(self):
        response = self.post(signed(bounce_event(self.sent)))
        self.assertEqual(response.status_code, 200)
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_BOUNCED)
        self.assertEqual(self.sent.bounce_class, SentEmail.BOUNCE_MAILBOX_MISSING)
        self.assertIn("User unknown", self.sent.delivery_detail)
        event = DeliveryEvent.objects.get()
        self.assertEqual((event.smtp_code, event.enhanced_code), ("550", "5.1.1"))

    def test_replaying_an_event_changes_nothing(self):
        body = signed(bounce_event(self.sent))
        self.post(body)
        response = self.post(body)
        self.assertEqual(response.json()["result"], "duplicate")
        self.assertEqual(DeliveryEvent.objects.count(), 1)

    def test_bad_signature_and_bad_json_are_refused(self):
        self.assertEqual(self.post(signed(bounce_event(self.sent), key="wrong")).status_code, 401)
        self.assertEqual(
            self.client.post(self.url, data="nope", content_type="application/json").status_code, 400
        )
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(DeliveryEvent.objects.exists())

    def test_matches_on_message_id_when_the_custom_variable_is_missing(self):
        event = bounce_event(self.sent)
        event["user-variables"] = {}
        self.post(signed(event))
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_BOUNCED)

    def test_other_apps_events_are_acknowledged_and_ignored(self):
        """The Mailgun domain is shared: an event we cannot match is not ours."""
        event = bounce_event(self.sent)
        event["user-variables"] = {"delivery_id": "42"}
        event["message"] = {"headers": {"message-id": "someone-elses@mail.example"}}
        response = self.post(signed(event))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "unmatched")
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_SENT)
        self.assertFalse(DeliveryEvent.objects.exists())

    def test_same_id_from_another_environment_is_not_matched(self):
        """Dev and production share the Mailgun domain and both number rows from 1."""
        event = bounce_event(self.sent)
        event["recipient"] = "someone-else@elsewhere.example"
        event["message"] = {"headers": {"message-id": "other-env@mail.example"}}
        response = self.post(signed(event))
        self.assertEqual(response.json()["result"], "unmatched")
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_SENT)

    def test_untracked_events_are_ignored(self):
        response = self.post(signed({"id": "o1", "event": "opened", "recipient": "a@b.example"}))
        self.assertEqual(response.json()["result"], "ignored")

    def test_delivered_after_a_bounce_does_not_undo_it(self):
        self.post(signed(bounce_event(self.sent)))
        delivered = {
            "id": "evt-delivered", "event": "delivered", "recipient": self.sent.company_email,
            "timestamp": time.time(), "user-variables": {"sent_email_id": str(self.sent.id)},
        }
        self.post(signed(delivered))
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_BOUNCED)
        self.assertEqual(DeliveryEvent.objects.count(), 2)

    def test_bounce_before_the_send_was_recorded_still_lands(self):
        """The bounce can beat the worker saving success and the Message-ID."""
        self.sent.success = False
        self.sent.mailgun_message_id = ""
        self.sent.save()
        self.post(signed(bounce_event(self.sent)))
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_BOUNCED)


class ParseEventTests(TestCase):
    def test_message_id_loses_its_brackets_and_recipient_is_normalised(self):
        event = parse_event({
            "id": "e", "event": "delivered", "recipient": " A@B.Example ",
            "timestamp": 1700000000.0,
            "message": {"headers": {"message-id": "<abc@mail.example>"}},
        })
        self.assertEqual((event.message_id, event.recipient), ("abc@mail.example", "a@b.example"))

    def test_enhanced_code_is_read_from_the_message(self):
        event = parse_event({
            "id": "e", "event": "failed", "severity": "permanent", "timestamp": 1.0,
            "delivery-status": {"code": 550, "message": "550-5.1.1 does not exist"},
        })
        self.assertEqual(event.enhanced_code, "5.1.1")


class UndeliverableAddressTests(TestCase):
    def setUp(self):
        self.company_type = CompanyType.objects.create(name="msp", label="MSP")
        self.template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<html><body>B</body></html>"
        )

    def make(self, email, status, bounce_class="", **kwargs):
        return SentEmail.objects.create(
            company_name="MSP", company_email=email, twenty_crm_id="crm-1", success=True,
            delivery_status=status, bounce_class=bounce_class, **kwargs,
        )

    def test_dead_addresses_are_found_but_soft_problems_are_not(self):
        self.make("Gone@x.example", SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING)
        self.make("nodomain@x.example", SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_DOMAIN_MISSING)
        self.make("full@x.example", SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_FULL)
        self.make("ok@x.example", SentEmail.DELIVERY_DELIVERED)
        self.make("spam@x.example", SentEmail.DELIVERY_COMPLAINED)
        self.make("refused@x.example", SentEmail.DELIVERY_SUPPRESSED)
        self.assertEqual(
            undeliverable_addresses(),
            {"gone@x.example", "nodomain@x.example", "spam@x.example", "refused@x.example"},
        )

    def test_a_later_delivery_clears_an_address(self):
        self.make("fixed@x.example", SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING)
        self.make("fixed@x.example", SentEmail.DELIVERY_DELIVERED)
        self.assertEqual(undeliverable_addresses(), set())

    def test_task_and_api_refuse_dead_addresses(self):
        self.make("gone@x.example", SentEmail.DELIVERY_BOUNCED, SentEmail.BOUNCE_MAILBOX_MISSING)
        with patch("emails.tasks.send_email") as mock_send:
            result = send_prospect_email(
                template_id=self.template.id, company_name="MSP", company_email="Gone@x.example",
                company_type_id=self.company_type.id, twenty_crm_id="crm-1",
            )
        self.assertEqual(result, {"status": "skipped", "reason": "undeliverable"})
        mock_send.assert_not_called()

        allowed, blocked = filter_recipients([Recipient("gone@x.example"), Recipient("ok@x.example")])
        self.assertEqual([r.company_email for r in blocked], ["gone@x.example"])
        self.assertEqual([r.company_email for r in allowed], ["ok@x.example"])

    @override_settings(EMAIL_DRY_RUN=False, MAILGUN_API_URL="https://mailgun.invalid/messages")
    @patch("emails.services.mailgun.httpx.post")
    def test_send_tags_the_message_with_the_sent_email_id(self, mock_post):
        mock_post.return_value.is_success = True
        mock_post.return_value.json.return_value = {"id": "<mg-1>"}
        send_email("ok@x.example", "S", "<p>B</p>", sent_email_id=77)
        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(data["v:sent_email_id"], "77")


class DeliveryApiTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        self.bounced = SentEmail.objects.create(
            company_name="Cabinet Mort", company_email="Gone@x.example", twenty_crm_id="crm-7",
            success=True, delivery_status=SentEmail.DELIVERY_BOUNCED,
            bounce_class=SentEmail.BOUNCE_MAILBOX_MISSING,
            delivery_detail="550 5.1.1 does not exist",
        )
        self.full = SentEmail.objects.create(
            company_name="Cabinet Plein", company_email="full@x.example", twenty_crm_id="crm-8",
            success=True, delivery_status=SentEmail.DELIVERY_BOUNCED,
            bounce_class=SentEmail.BOUNCE_MAILBOX_FULL,
        )
        self.ok = SentEmail.objects.create(
            company_name="OK", company_email="ok@x.example", twenty_crm_id="crm-1",
            success=True, delivery_status=SentEmail.DELIVERY_DELIVERED,
        )

    def ids(self, **params):
        body = self.client.get("/api/emails/sent", params).json()
        return {row["id"] for row in body}

    def test_list_filters(self):
        self.assertEqual(self.ids(delivery="problem"), {self.bounced.id, self.full.id})
        self.assertEqual(self.ids(delivery="mailbox_missing"), {self.bounced.id})
        self.assertEqual(self.ids(delivery="delivered"), {self.ok.id})
        row = self.client.get("/api/emails/sent", {"delivery": "mailbox_missing"}).json()[0]
        self.assertEqual(row["bounce_class"], "mailbox_missing")
        self.assertIn("5.1.1", row["delivery_detail"])

    def test_stats_do_not_count_bounced_emails_as_received(self):
        body = self.client.get("/api/email-stats/by-address").json()
        self.assertEqual(set(body), {"ok@x.example"})
        self.assertEqual(set(self.client.get("/api/email-stats").json()), {"crm-1"})

    def test_problem_addresses_json_and_csv(self):
        dead = self.client.get("/api/emails/problem-addresses").json()
        self.assertEqual([r["address"] for r in dead], ["gone@x.example"])
        self.assertEqual(dead[0]["twenty_crm_id"], "crm-7")

        wider = self.client.get("/api/emails/problem-addresses", {"all": "true"}).json()
        self.assertEqual({r["address"] for r in wider}, {"gone@x.example", "full@x.example"})

        response = self.client.get("/api/emails/problem-addresses.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        text = response.content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0].split(",")[:3], ["address", "company", "twenty_id"])
        self.assertIn("gone@x.example,Cabinet Mort,crm-7,bounced,mailbox_missing", lines[1])
        self.assertEqual(len(lines), 2)

    def test_problem_addresses_require_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/emails/problem-addresses").status_code, 401)
        self.assertEqual(self.client.get("/api/emails/problem-addresses.csv").status_code, 401)

    @patch("emails.api.fetch_email_from_sent", return_value=None)
    def test_preview_carries_delivery_and_events(self, _imap):
        template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<p>B</p>"
        )
        self.bounced.template = template
        self.bounced.save()
        DeliveryEvent.objects.create(
            sent_email=self.bounced, provider_event_id="e1", kind="failed", severity="permanent",
            smtp_code="550", enhanced_code="5.1.1", detail="550 does not exist",
            occurred_at=self.bounced.sent_at,
        )
        with patch("emails.api.build_context", return_value={"company_name": "x"}):
            body = self.client.get(f"/api/emails/sent/{self.bounced.id}/preview").json()
        self.assertEqual(body["delivery_status"], "bounced")
        self.assertEqual(body["bounce_class"], "mailbox_missing")
        self.assertEqual([e["enhanced_code"] for e in body["events"]], ["5.1.1"])


@override_settings(MAILGUN_DOMAIN="mail.example", MAILGUN_API_KEY="k", MAILGUN_API_URL="https://api.eu.mailgun.net/v3/mail.example/messages")
class BackfillMailgunEventsTests(TestCase):
    def setUp(self):
        self.sent = SentEmail.objects.create(
            company_name="MSP", company_email="dead@x.example", twenty_crm_id="crm-1",
            success=True, mailgun_message_id="<mg-1@mail.example>",
        )

    def run_backfill(self, pages, *args):
        """pages: {"bounces": [...], "complaints": [...], "events": [...]} items."""
        def fake_paginate(http, url, params=None):
            return iter(pages.get(url.rsplit("/", 1)[1], []))

        with patch("emails.management.commands.backfill_mailgun_events.paginate", fake_paginate):
            out = StringIO()
            call_command("backfill_mailgun_events", *args, stdout=out)
        return out.getvalue()

    def test_bounce_list_marks_the_address_and_is_idempotent(self):
        item = {
            "address": "Dead@x.example", "code": "550",
            "error": "550 5.1.1 The email account does not exist",
            "created_at": "Tue, 01 Jan 2030 10:00:00 UTC",
        }
        self.run_backfill({"bounces": [item]}, "--skip-events")
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.bounce_class, SentEmail.BOUNCE_MAILBOX_MISSING)
        out = self.run_backfill({"bounces": [item]}, "--skip-events")
        self.assertIn("already known 1", out)
        self.assertEqual(DeliveryEvent.objects.count(), 1)

    def test_bounce_for_an_address_we_never_mailed_is_ignored(self):
        item = {"address": "stranger@x.example", "code": "550", "error": "5.1.1",
                "created_at": "Tue, 01 Jan 2030 10:00:00 UTC"}
        out = self.run_backfill({"bounces": [item]}, "--skip-events")
        self.assertIn("unmatched 1", out)

    def test_events_are_matched_on_message_id(self):
        events = [
            {"id": "d1", "event": "delivered", "recipient": "dead@x.example",
             "timestamp": 1700000000.0, "message": {"headers": {"message-id": "mg-1@mail.example"}}},
            {"id": "o1", "event": "opened", "recipient": "dead@x.example", "timestamp": 1.0},
        ]
        self.run_backfill({"events": events}, "--skip-lists")
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.delivery_status, SentEmail.DELIVERY_DELIVERED)


@override_settings(
    MAILGUN_DOMAIN="mail.example", SITE_URL="https://prospect.example",
    MAILGUN_API_KEY="k", MAILGUN_API_URL="https://api.eu.mailgun.net/v3/mail.example/messages",
)
class RegisterMailWebhooksTests(TestCase):
    OURS = "https://prospect.example/api/webhooks/mailgun"

    def run_command(self, registered, *args):
        http = MagicMock()
        http.__enter__.return_value = http
        http.get.return_value = MagicMock(status_code=200, json=lambda: {"webhooks": registered})
        http.put.return_value = http.post.return_value = MagicMock(status_code=200)
        with patch("emails.management.commands.register_mail_webhooks.client", return_value=http):
            call_command("register_mail_webhooks", *args, stdout=StringIO())
        return http

    def test_adds_our_url_next_to_the_other_apps_without_replacing_it(self):
        other = "https://clinic.example/api/v2/mail/events/mailgun"
        http = self.run_command({"delivered": {"urls": [other]}})
        put = http.put.call_args
        self.assertTrue(put.args[0].endswith("/webhooks/delivered"))
        self.assertEqual(put.kwargs["data"]["url"], [other, self.OURS])
        # Events with nothing registered are created, not PUT.
        self.assertEqual(http.post.call_count, 3)

    def test_dry_run_changes_nothing_and_registered_urls_are_skipped(self):
        http = self.run_command({}, "--dry-run")
        http.post.assert_not_called()
        http.put.assert_not_called()
        everything = {e: {"urls": [self.OURS]} for e in ("delivered", "permanent_fail", "temporary_fail", "complained")}
        http = self.run_command(everything)
        http.post.assert_not_called()
        http.put.assert_not_called()


class SendDeliveryTestCommandTests(TestCase):
    def run_command(self, *args):
        call_command("send_delivery_test", *args, stdout=StringIO())

    def test_only_plain_medica_addresses_are_safe(self):
        from .management.commands.send_delivery_test import is_safe_recipient

        self.assertTrue(is_safe_recipient("test@medica.im"))
        self.assertTrue(is_safe_recipient("Test@MEDICA.IM"))
        for bad in [
            "x@gmail.com", "x@medica.im.evil.example", "x@evil-medica.im", "x@sub.medica.im",
            "a@b.com@medica.im", '"a@b.com"@medica.im', "x@medica.im, y@gmail.com", "Name <x@medica.im>", " x@medica.im", "@medica.im", "medica.im", "",
        ]:
            with self.subTest(address=bad):
                self.assertFalse(is_safe_recipient(bad))

    @override_settings(DEBUG=True)
    @patch("emails.management.commands.send_delivery_test.send_email")
    def test_a_foreign_address_is_refused_before_anything_is_sent(self, mock_send):
        with self.assertRaises(CommandError):
            self.run_command("ok@medica.im", "someone@gmail.com")
        mock_send.assert_not_called()
        self.assertFalse(SentEmail.objects.exists())

    @override_settings(DEBUG=False)
    @patch("emails.management.commands.send_delivery_test.send_email")
    def test_refuses_outside_dev(self, mock_send):
        with self.assertRaises(CommandError):
            self.run_command("ok@medica.im")
        mock_send.assert_not_called()

    @override_settings(DEBUG=True, MAILGUN_API_URL="https://x.invalid/messages", MAILGUN_SENDING_KEY="k")
    @patch("emails.management.commands.send_delivery_test.send_email")
    def test_sends_live_to_a_random_nonexistent_mailbox_and_tags_the_row(self, mock_send):
        mock_send.return_value = {"id": "<mg-test@mail.medica.im>"}
        self.run_command()
        sent = SentEmail.objects.get()
        self.assertTrue(sent.company_email.startswith("delivery-test-"))
        self.assertTrue(sent.company_email.endswith("@medica.im"))
        self.assertTrue(sent.success)
        self.assertEqual(sent.mailgun_message_id, "<mg-test@mail.medica.im>")
        kwargs = mock_send.call_args.kwargs
        self.assertIs(kwargs["dry_run"], False)
        self.assertEqual(kwargs["sent_email_id"], sent.id)
        self.run_command("--clear")
        self.assertFalse(SentEmail.objects.exists())

    @override_settings(EMAIL_DRY_RUN=True, MAILGUN_API_URL="https://mailgun.invalid/messages")
    @patch("emails.services.mailgun.httpx.post")
    def test_dry_run_can_be_overridden_per_call_and_stays_on_by_default(self, mock_post):
        mock_post.return_value.is_success = True
        mock_post.return_value.json.return_value = {"id": "<live>"}
        self.assertTrue(send_email("a@medica.im", "S", "B")["id"].startswith("<dry-run."))
        mock_post.assert_not_called()
        self.assertEqual(send_email("a@medica.im", "S", "B", dry_run=False)["id"], "<live>")
        mock_post.assert_called_once()


# --- Rejected emails do not count as received --------------------------------

from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone


class ReceivedCountTests(TestCase):
    """What /emails/send shows as 'emails received' per address."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        self.now = timezone.now()

    def make(self, status, days_ago, success=True, email="a@x.example", crm="crm-1", **kwargs):
        row = SentEmail.objects.create(
            company_name="MSP", company_email=email, twenty_crm_id=crm,
            success=success, delivery_status=status, **kwargs,
        )
        SentEmail.objects.filter(pk=row.pk).update(sent_at=self.now - timedelta(days=days_ago))
        row.refresh_from_db()
        return row

    def stats(self, url="/api/email-stats/by-address", key="a@x.example"):
        return self.client.get(url).json().get(key)

    def test_only_emails_that_reached_the_recipient_count(self):
        for status in ("sent", "delivered", "deferred", "complained"):
            self.make(status, 10)
        self.make("bounced", 9, bounce_class="mailbox_missing")
        self.make("suppressed", 8)
        self.make("sent", 7, success=False)
        self.assertEqual(self.stats()["total_sent"], 4)
        self.assertEqual(self.stats("/api/email-stats", "crm-1")["total_sent"], 4)

    def test_last_sent_date_ignores_rejected_emails(self):
        counted = self.make("delivered", 30)
        self.make("suppressed", 5)
        self.make("bounced", 2, bounce_class="mailbox_full")
        last = self.stats()["last_sent_at"][:19]
        self.assertEqual(last, counted.sent_at.isoformat()[:19])

    def test_an_address_where_everything_was_rejected_has_no_entry(self):
        self.make("bounced", 3, bounce_class="mailbox_missing")
        self.make("suppressed", 1)
        self.assertIsNone(self.stats())


@override_settings(MAILGUN_DOMAIN="mail.example", MAILGUN_API_KEY="k", MAILGUN_API_URL="https://api.eu.mailgun.net/v3/mail.example/messages")
class InferredRefusalTests(TestCase):
    LISTED = "Tue, 01 Jan 2030 10:00:00 UTC"

    def setUp(self):
        self.listed_at = datetime(2030, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        self.before = self.make(-40)
        self.after_old = self.make(+20)
        self.after_older = self.make(+90)
        self.observed = self.make(+30, delivery_status=SentEmail.DELIVERY_DELIVERED)
        self.other = self.make(+20, email="other@x.example")

    def make(self, days_from_listing, email="dead@x.example", **kwargs):
        row = SentEmail.objects.create(
            company_name="MSP", company_email=email, twenty_crm_id="crm-1", success=True,
            mailgun_message_id=f"<{email}-{days_from_listing}@mail.example>", **kwargs,
        )
        SentEmail.objects.filter(pk=row.pk).update(
            sent_at=self.listed_at + timedelta(days=days_from_listing)
        )
        row.refresh_from_db()
        return row

    def backfill(self, bounces=(), complaints=()):
        pages = {"bounces": list(bounces), "complaints": list(complaints)}

        def fake_paginate(http, url, params=None):
            return iter(pages.get(url.rsplit("/", 1)[1], []))

        with patch("emails.management.commands.backfill_mailgun_events.paginate", fake_paginate):
            out = StringIO()
            call_command("backfill_mailgun_events", "--skip-events", stdout=out)
        return out.getvalue()

    def bounce_item(self, address="dead@x.example"):
        return {
            "address": address, "code": "550", "created_at": self.LISTED,
            "error": "550 5.1.1 The email account does not exist",
        }

    def status(self, row):
        row.refresh_from_db()
        return row.delivery_status

    def test_later_emails_to_a_bounced_address_become_refused_and_stop_counting(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        out = self.backfill(bounces=[self.bounce_item()])

        self.assertEqual(self.status(self.before), SentEmail.DELIVERY_BOUNCED)
        self.assertEqual(self.before.bounce_class, SentEmail.BOUNCE_MAILBOX_MISSING)
        self.assertEqual(self.status(self.after_old), SentEmail.DELIVERY_SUPPRESSED)
        self.assertEqual(self.status(self.after_older), SentEmail.DELIVERY_SUPPRESSED)
        self.assertIn("Déduit", self.after_old.delivery_detail)
        self.assertIn("inferred refused 2", out)

        # An outcome we actually observed is never overridden.
        self.assertEqual(self.status(self.observed), SentEmail.DELIVERY_DELIVERED)
        # Other addresses are untouched.
        self.assertEqual(self.status(self.other), SentEmail.DELIVERY_SENT)

        stats = self.client.get("/api/email-stats/by-address").json()
        self.assertEqual(stats["dead@x.example"]["total_sent"], 1)  # only the delivered one
        self.assertEqual(stats["other@x.example"]["total_sent"], 1)

    def test_rerunning_changes_nothing(self):
        self.backfill(bounces=[self.bounce_item()])
        events = DeliveryEvent.objects.count()
        out = self.backfill(bounces=[self.bounce_item()])
        self.assertIn("inferred refused 0", out)
        self.assertEqual(DeliveryEvent.objects.count(), events)

    def test_complaints_refuse_later_emails_too(self):
        item = {"address": "dead@x.example", "created_at": self.LISTED}
        self.backfill(complaints=[item])
        self.assertEqual(self.status(self.before), SentEmail.DELIVERY_COMPLAINED)
        self.assertEqual(self.status(self.after_old), SentEmail.DELIVERY_SUPPRESSED)
        self.assertIn("plainte", self.after_old.delivery_detail)

    def test_emails_are_refused_even_when_none_was_sent_before_the_listing(self):
        """Another app got the address listed; we only mailed it afterwards."""
        SentEmail.objects.filter(pk=self.before.pk).delete()
        self.backfill(bounces=[self.bounce_item()])
        self.assertEqual(self.status(self.after_old), SentEmail.DELIVERY_SUPPRESSED)

    def test_the_csv_keeps_the_original_reason_after_later_refusals(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        self.backfill(bounces=[self.bounce_item()])
        rows = self.client.get("/api/emails/problem-addresses").json()
        self.assertEqual([r["address"] for r in rows], ["dead@x.example"])
        self.assertEqual(rows[0]["delivery_status"], "suppressed")
        self.assertEqual(rows[0]["bounce_class"], "mailbox_missing")
        self.assertIn("5.1.1", rows[0]["delivery_detail"])
        csv_text = self.client.get("/api/emails/problem-addresses.csv").content.decode("utf-8-sig")
        self.assertIn("mailbox_missing", csv_text)
