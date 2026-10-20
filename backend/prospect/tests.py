from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from emails.models import CompanyType, EmailTemplate
from prospect.urls import api

# The only Ninja routes an anonymous caller may reach.
PUBLIC_OPERATIONS = {"auth_login", "auth_logout"}


def ninja_operations():
    """Every (view name, auth callbacks) pair registered on the API."""
    for _prefix, router in api._routers:
        for path_view in router.path_operations.values():
            for operation in path_view.operations:
                yield operation.view_func.__name__, operation.auth_callbacks


class EveryRouteRequiresAuthTests(TestCase):
    def test_only_login_and_logout_are_public(self):
        names = set()
        for name, auth_callbacks in ninja_operations():
            names.add(name)
            if name in PUBLIC_OPERATIONS:
                self.assertEqual(auth_callbacks, [], name)
            else:
                self.assertNotEqual(auth_callbacks, [], f"{name} has no auth")
        # Guards against the walk silently finding nothing.
        self.assertTrue(PUBLIC_OPERATIONS <= names)
        self.assertIn("send_emails", names)


class AnonymousAccessTests(TestCase):
    @patch("emails.api.fetch_companies")
    def test_companies_are_refused(self, mock_fetch):
        response = self.client.get("/api/companies")
        self.assertEqual(response.status_code, 401)
        mock_fetch.assert_not_called()

    @patch("emails.api.send_prospect_email")
    def test_send_is_refused_and_nothing_is_queued(self, mock_task):
        response = self.client.post(
            "/api/emails/send",
            data={"template_id": 1, "recipients": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        mock_task.delay.assert_not_called()

    def test_me_is_refused(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_docs_redirect_to_admin_login(self):
        response = self.client.get("/api/docs")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_unsubscribe_page_stays_public(self):
        # A plain Django view outside the Ninja API: recipients are never logged in.
        response = self.client.get("/api/unsubscribe/not-a-token")
        self.assertEqual(response.status_code, 200)


class SessionAccessTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("operator", password="s3cret-pass")

    def test_login_then_me(self):
        response = self.client.post(
            "/api/auth/login",
            data={"username": "operator", "password": "s3cret-pass"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").json()["username"], "operator")

    def test_wrong_password_gets_no_session(self):
        self.client.post(
            "/api/auth/login",
            data={"username": "operator", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    @patch("emails.api.send_prospect_email")
    def test_post_needs_no_csrf_token(self, mock_task):
        # The SvelteKit server forwards only the sessionid cookie, never a CSRF
        # token, so a session POST must go through with CSRF checks enforced.
        company_type = CompanyType.objects.create(name="msp", label="MSP")
        template = EmailTemplate.objects.create(
            name="T", subject_template="Bonjour", html_body="<html><body>B</body></html>"
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(get_user_model().objects.get(username="operator"))
        response = client.post(
            "/api/emails/send",
            data={
                "template_id": template.id,
                "recipients": [{
                    "company_name": "MSP du Marais",
                    "company_email": "ok@example.fr",
                    "company_type_id": company_type.id,
                    "twenty_crm_id": "crm-1",
                }],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_task.delay.call_count, 1)
