from unittest.mock import patch

from django.contrib.auth import get_user_model
from axes.models import AccessAttempt, AccessFailureLog
from django.test import Client, TestCase
from django.utils import timezone

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


class LoginLockoutTests(TestCase):
    """django-axes: 5 failures lock a username for 15 minutes (settings.AXES_*)."""

    def setUp(self):
        get_user_model().objects.create_user(
            "operator", password="s3cret-pass", is_staff=True
        )

    def _api_login(self, password, username="operator", **extra):
        return self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
            content_type="application/json",
            **extra,
        )

    def _rewind(self, minutes):
        """Pretend the recorded failures happened `minutes` earlier."""
        for attempt in AccessAttempt.objects.all():
            attempt.attempt_time -= timezone.timedelta(minutes=minutes)
            attempt.save()

    def test_fifth_failure_locks_even_the_right_password_out(self):
        for _ in range(4):
            self.assertEqual(self._api_login("wrong").status_code, 401)
        self.assertEqual(self._api_login("wrong").status_code, 429)
        self.assertEqual(self._api_login("s3cret-pass").status_code, 429)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_lock_lifts_after_the_cool_off(self):
        for _ in range(5):
            self._api_login("wrong")
        self._rewind(16)
        self.assertEqual(self._api_login("s3cret-pass").status_code, 200)

    def test_attempts_during_the_lock_do_not_extend_it(self):
        for _ in range(5):
            self._api_login("wrong")
        self._rewind(10)
        self.assertEqual(self._api_login("wrong").status_code, 429)
        self._rewind(6)
        self.assertEqual(self._api_login("s3cret-pass").status_code, 200)

    def test_success_resets_the_count(self):
        for _ in range(4):
            self._api_login("wrong")
        self.assertEqual(self._api_login("s3cret-pass").status_code, 200)
        self.client.post("/api/auth/logout")
        for _ in range(4):
            self.assertEqual(self._api_login("wrong").status_code, 401)

    def test_unknown_usernames_are_locked_too(self):
        for _ in range(5):
            self._api_login("wrong", username="nobody")
        self.assertEqual(self._api_login("wrong", username="nobody").status_code, 429)

    def test_admin_and_app_logins_share_one_count(self):
        for _ in range(5):
            self.client.post("/admin/login/", {"username": "operator", "password": "wrong"})
        self.assertEqual(self._api_login("s3cret-pass").status_code, 429)

    def test_failures_are_logged_with_the_nginx_client_address(self):
        self._api_login("wrong", HTTP_X_REAL_IP="203.0.113.7")
        failure = AccessFailureLog.objects.get()
        self.assertEqual(failure.username, "operator")
        self.assertEqual(failure.ip_address, "203.0.113.7")
