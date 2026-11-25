"""MSSanté addresses are kept in Twenty but never offered, sent to or reported."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import CompanyType, EmailTemplate, SentEmail
from .services import problems
from .services.closed_networks import is_closed_network
from .services.delivery import problem_addresses
from .services.unsubscribe import filter_recipients
from .tasks import send_prospect_email

MSSANTE = "cpts-du-plateau@paca.mssante.fr"


class Recipient:
    def __init__(self, company_email):
        self.company_email = company_email


class IsClosedNetworkTests(TestCase):
    def test_mssante_and_its_subdomains(self):
        for address in (MSSANTE, "x@mssante.fr", " X@AURA.MSSANTE.FR ", "a@b.c.mssante.fr"):
            self.assertTrue(is_closed_network(address), address)

    def test_lookalikes_and_ordinary_addresses_are_not(self):
        for address in (
            "x@gmail.com", "x@notmssante.fr", "x@mssante.fr.example.com", "mssante.fr", "", "x@mssante.com",
        ):
            self.assertFalse(is_closed_network(address), address)


class ClosedNetworkSendTests(TestCase):
    def setUp(self):
        self.company_type = CompanyType.objects.create(name="cpts", label="CPTS")
        self.template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<html><body>B</body></html>"
        )

    def test_filter_recipients_blocks_them(self):
        allowed, blocked = filter_recipients([Recipient(MSSANTE), Recipient("ok@x.example")])
        self.assertEqual([r.company_email for r in blocked], [MSSANTE])
        self.assertEqual([r.company_email for r in allowed], ["ok@x.example"])

    def test_the_task_refuses_even_when_queued_before_the_rule(self):
        with patch("emails.tasks.send_email") as mock_send:
            result = send_prospect_email(
                template_id=self.template.id, company_name="CPTS", company_email=MSSANTE,
                company_type_id=self.company_type.id, twenty_crm_id="crm-1",
            )
        self.assertEqual(result, {"status": "skipped", "reason": "closed_network"})
        mock_send.assert_not_called()
        self.assertEqual(SentEmail.objects.count(), 0)

    @patch("emails.services.dispatch.send_prospect_email")
    def test_the_send_api_skips_them_and_reports_it(self, mock_task):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        recipient = {
            "company_name": "CPTS", "company_type_id": self.company_type.id, "twenty_crm_id": "crm-1",
        }
        response = self.client.post(
            "/api/emails/send",
            data={
                "template_id": self.template.id,
                "recipients": [
                    {**recipient, "company_email": MSSANTE},
                    {**recipient, "company_email": "ok@x.example"},
                ],
            },
            content_type="application/json",
        )
        body = response.json()
        self.assertEqual((body["queued"], body["skipped_emails"]), (1, [MSSANTE]))
        self.assertEqual(mock_task.delay.call_count, 1)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ClosedNetworkReportTests(TestCase):
    def setUp(self):
        for address in (MSSANTE, "gone@x.example"):
            SentEmail.objects.create(
                company_name="CPTS", company_email=address, twenty_crm_id="crm-1", success=True,
                delivery_status=SentEmail.DELIVERY_SUPPRESSED,
            )
        self.addCleanup(problems.cache.clear)

    def test_neither_report_lists_them(self):
        people = [
            {"id": "p1", "name": "A", "job_title": "", "primary_email": MSSANTE, "additional_emails": [],
             "company_id": "co-1", "company_name": "", "company_type": None},
            {"id": "p2", "name": "B", "job_title": "", "primary_email": "gone@x.example", "additional_emails": [],
             "company_id": "co-1", "company_name": "", "company_type": None},
        ]
        with patch("emails.services.problems.fetch_people", return_value=people), \
                patch("emails.services.problems.fetch_companies", return_value=[]):
            rows = problems.current_problem_addresses("all")["rows"]
        self.assertEqual([r["address"] for r in rows], ["gone@x.example"])
        self.assertEqual([r["address"] for r in problem_addresses()], ["gone@x.example"])
