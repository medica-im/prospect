from unittest.mock import patch

from django.core import signing
from django.test import TestCase

from .models import CompanyType, EmailTemplate, SentEmail, Unsubscribe
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
