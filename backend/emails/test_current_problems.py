"""Addresses still in Twenty whose latest send failed (services/problems.py)."""

import csv
import io
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import ApiToken, MailgunSuppression, SentEmail
from .services import problems
from .services.problems import advise
from .services.api_tokens import find_token, hash_token
from .services.suppressions import record_list_item
from .services.twenty_crm import fetch_people

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def person(pid, primary="", additional=(), name="Ada Martin", company_id="co-1", job_title="Président"):
    return {
        "id": pid, "name": name, "job_title": job_title, "primary_email": primary,
        "additional_emails": list(additional), "company_id": company_id,
        "company_name": "", "company_type": None,
    }


def company(cid="co-1", name="CPTS Val", emails=(), company_type="CPTS"):
    return {"id": cid, "name": name, "emails": list(emails), "company_type": company_type}


@override_settings(CACHES=LOCMEM, TWENTY_API_URL="https://twenty.example")
class CurrentProblemsTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.people = []
        self.companies = [company()]
        patches = [
            patch("emails.services.problems.fetch_people", side_effect=lambda: self.people),
            patch("emails.services.problems.fetch_companies", side_effect=lambda: self.companies),
        ]
        self.fetch_people, self.fetch_companies = (p.start() for p in patches)
        for p in patches:
            self.addCleanup(p.stop)
        self.addCleanup(problems.cache.clear)

    def send(self, email, days_ago, status=SentEmail.DELIVERY_DELIVERED, success=True, **kwargs):
        row = SentEmail.objects.create(
            company_name="CPTS Val", company_email=email, twenty_crm_id="not-the-person-id",
            success=success, delivery_status=status, **kwargs,
        )
        SentEmail.objects.filter(pk=row.pk).update(sent_at=self.now - timedelta(days=days_ago))
        return row

    def bounce(self, email, days_ago, bounce_class=SentEmail.BOUNCE_MAILBOX_MISSING, detail="550 5.1.1 no"):
        return self.send(
            email, days_ago, SentEmail.DELIVERY_BOUNCED, bounce_class=bounce_class, delivery_detail=detail,
        )

    def result(self, severity="all", **kwargs):
        return problems.current_problem_addresses(severity=severity, **kwargs)

    def rows(self, severity="all"):
        return {row["address"]: row for row in self.result(severity)["rows"]}

    # --- latest attempt rule ---

    def test_bounced_then_delivered_is_fine(self):
        self.people = [person("p1", "a@x.example")]
        self.bounce("a@x.example", 20)
        self.send("a@x.example", 5)
        self.assertEqual(self.rows(), {})

    def test_delivered_then_bounced_is_a_problem(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 20)
        self.bounce("a@x.example", 5)
        row = self.rows()["a@x.example"]
        self.assertEqual((row["status"], row["severity"]), ("bounced", "dead"))
        self.assertEqual(row["bounce_class"], "mailbox_missing")
        self.assertEqual(row["smtp_detail"], "550 5.1.1 no")

    def test_refused_send_is_troublesome(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 5, success=False, error_message="Mailgun 400: bad domain")
        row = self.rows()["a@x.example"]
        self.assertEqual((row["status"], row["severity"]), ("send_failed", "troublesome"))
        self.assertEqual(row["smtp_detail"], "Mailgun 400: bad domain")
        self.assertEqual(self.rows("dead"), {})

    def test_deferred_is_listed_as_pending_not_dead(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 1, SentEmail.DELIVERY_DEFERRED, delivery_detail="451 try later")
        self.assertEqual(self.rows()["a@x.example"]["severity"], "pending")
        self.assertEqual(self.rows("dead"), {})

    def test_no_news_yet_is_not_a_problem(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 1, SentEmail.DELIVERY_SENT)
        self.assertEqual(self.rows(), {})

    def test_severity_dead_keeps_only_dead_addresses(self):
        self.people = [
            person("p1", "dead@x.example"), person("p2", "full@x.example"),
            person("p3", "spam@x.example"), person("p4", "gone-domain@x.example"),
        ]
        self.bounce("dead@x.example", 3)
        self.bounce("full@x.example", 3, SentEmail.BOUNCE_MAILBOX_FULL)
        self.send("spam@x.example", 3, SentEmail.DELIVERY_COMPLAINED)
        self.bounce("gone-domain@x.example", 3, SentEmail.BOUNCE_DOMAIN_MISSING)
        self.assertEqual(
            set(self.rows("dead")), {"dead@x.example", "spam@x.example", "gone-domain@x.example"},
        )
        self.assertEqual(set(self.rows("all")), set(self.rows("dead")) | {"full@x.example"})

    def test_addresses_are_matched_case_insensitively_and_never_by_crm_id(self):
        self.people = [person("p1", "Ada.Martin@X.Example")]
        self.bounce("ada.martin@x.example ", 3)
        self.assertEqual(list(self.rows()), ["ada.martin@x.example"])

    # --- what counts as "in Twenty" ---

    def test_an_address_no_longer_in_twenty_is_excluded(self):
        self.people = [person("p1", "kept@x.example")]
        self.bounce("kept@x.example", 3)
        self.bounce("removed@x.example", 3)
        self.assertEqual(list(self.rows()), ["kept@x.example"])

    def test_an_address_never_mailed_is_not_listed(self):
        self.people = [person("p1", "new@x.example")]
        self.assertEqual(self.rows(), {})

    def test_additional_emails_and_company_email_are_included(self):
        self.people = [person("p1", "main@x.example", additional=["extra@x.example", "MAIN@x.example"])]
        self.companies = [company(emails=["desk@x.example"])]
        for address in ("main@x.example", "extra@x.example", "desk@x.example"):
            self.bounce(address, 3)
        rows = self.rows()
        self.assertEqual(rows["main@x.example"]["where"], "person_primary")
        self.assertEqual(rows["extra@x.example"]["where"], "person_additional")
        self.assertEqual(rows["desk@x.example"]["where"], "company")
        self.assertEqual(len(self.result()["rows"]), 3)  # primary repeated as additional counts once

    def test_row_carries_the_person_and_company_and_links_to_twenty(self):
        self.people = [person("p1", "a@x.example", name="Ada Martin", job_title="Coordinateur")]
        self.companies = [company(emails=["desk@x.example"], name="CPTS Val de Siagne")]
        self.bounce("a@x.example", 3)
        self.bounce("desk@x.example", 3)
        rows = self.rows()
        self.assertEqual(
            {key: rows["a@x.example"][key] for key in (
                "person_id", "person_name", "job_title", "company_id", "company_name",
                "company_type", "twenty_url",
            )},
            {
                "person_id": "p1", "person_name": "Ada Martin", "job_title": "Coordinateur",
                "company_id": "co-1", "company_name": "CPTS Val de Siagne", "company_type": "CPTS",
                "twenty_url": "https://twenty.example/object/person/p1",
            },
        )
        self.assertEqual(rows["desk@x.example"]["person_id"], "")
        self.assertEqual(rows["desk@x.example"]["twenty_url"], "https://twenty.example/object/company/co-1")

    def test_a_person_without_a_known_company_still_lists(self):
        self.people = [person("p1", "a@x.example", company_id="")]
        self.bounce("a@x.example", 3)
        row = self.rows()["a@x.example"]
        self.assertEqual((row["company_id"], row["company_name"]), ("", ""))

    # --- suppression ---

    def test_suppressed_shows_the_original_bounce(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 30)
        self.bounce("a@x.example", 20, detail="550 5.1.1 original")
        self.send("a@x.example", 5, SentEmail.DELIVERY_SUPPRESSED, delivery_detail="suppress-bounce")
        row = self.rows()["a@x.example"]
        self.assertEqual((row["status"], row["severity"]), ("suppressed", "dead"))
        self.assertEqual((row["bounce_class"], row["smtp_detail"]), ("mailbox_missing", "550 5.1.1 original"))

    def test_suppressed_without_an_original_bounce_says_unknown(self):
        self.people = [person("p1", "a@x.example")]
        self.send("a@x.example", 5, SentEmail.DELIVERY_SUPPRESSED)
        row = self.rows()["a@x.example"]
        self.assertEqual((row["bounce_class"], row["smtp_detail"]), ("", "unknown (Mailgun suppression)"))

    def test_suppressed_without_a_bounce_of_ours_uses_mailgun_list_details(self):
        self.people = [person("p1", "a@x.example"), person("p2", "b@x.example")]
        self.send("a@x.example", 5, SentEmail.DELIVERY_SUPPRESSED)
        self.send("b@x.example", 5, SentEmail.DELIVERY_SUPPRESSED)
        record_list_item("bounce", {
            "address": "A@x.example", "code": "550", "created_at": "Tue, 01 Jan 2030 10:00:00 UTC",
            "error": "5.1.1 The email account does not exist.\n5.1.1 Check the address",
        })
        record_list_item("complaint", {"address": "b@x.example", "created_at": "Tue, 01 Jan 2030 10:00:00 UTC"})
        rows = self.rows()
        self.assertEqual(rows["a@x.example"]["bounce_class"], "mailbox_missing")
        self.assertEqual(
            rows["a@x.example"]["smtp_detail"],
            "550 5.1.1 The email account does not exist. 5.1.1 Check the address",
        )
        self.assertEqual(rows["b@x.example"]["bounce_class"], "")
        self.assertEqual(rows["b@x.example"]["smtp_detail"], "Spam complaint listed by Mailgun on 2030-01-01")

    def test_our_own_bounce_wins_over_mailgun_list(self):
        self.people = [person("p1", "a@x.example")]
        self.bounce("a@x.example", 20, SentEmail.BOUNCE_BLOCKED, "550 5.7.1 ours")
        self.send("a@x.example", 5, SentEmail.DELIVERY_SUPPRESSED)
        record_list_item("bounce", {"address": "a@x.example", "code": "550", "error": "5.1.1 theirs"})
        row = self.rows()["a@x.example"]
        self.assertEqual((row["bounce_class"], row["smtp_detail"]), ("blocked", "550 5.7.1 ours"))

    # --- what to do about it ---

    def test_each_row_says_what_to_do(self):
        self.people = [person(f"p{i}", f"a{i}@x.example") for i in range(7)]
        self.bounce("a0@x.example", 3)  # no such user
        self.bounce("a1@x.example", 3, SentEmail.BOUNCE_DOMAIN_MISSING, "498 No MX for x.example")
        self.bounce("a2@x.example", 3, SentEmail.BOUNCE_MAILBOX_FULL, "552 quota exceeded")
        self.bounce("a3@x.example", 3, SentEmail.BOUNCE_BLOCKED, "550 5.7.1 rejected")
        self.send("a4@x.example", 3, success=False, error_message="No French definite article")
        self.send("a5@x.example", 1, SentEmail.DELIVERY_DEFERRED, delivery_detail="421 later")
        self.bounce("a6@x.example", 3, SentEmail.BOUNCE_MAILBOX_MISSING, "525 5.7.13 Disabled recipient address")
        got = {a: (r["action"], r["reason"]) for a, r in self.rows().items()}
        self.assertEqual(got, {
            "a0@x.example": ("remove", "mailbox_unknown"),
            "a1@x.example": ("remove", "domain_gone"),
            "a2@x.example": ("retry", "mailbox_full"),
            "a3@x.example": ("review", "policy_block"),
            "a4@x.example": ("fix", "our_error"),
            "a5@x.example": ("retry", "retrying"),
            "a6@x.example": ("remove", "account_closed"),
        })

    def test_action_filter_overrides_severity(self):
        self.people = [person("p1", "dead@x.example"), person("p2", "old@x.example"), person("p3", "full@x.example")]
        self.bounce("dead@x.example", 3)
        # Stored before the classifier knew Exchange's answer: severity says troublesome,
        # the class was fixed since, so advice follows the class.
        self.bounce("old@x.example", 3, SentEmail.BOUNCE_MAILBOX_MISSING)
        self.bounce("full@x.example", 3, SentEmail.BOUNCE_MAILBOX_FULL)
        result = problems.current_problem_addresses(action="remove")
        self.assertEqual({r["address"] for r in result["rows"]}, {"dead@x.example", "old@x.example"})
        self.assertEqual(problems.current_problem_addresses(action="retry")["count"], 1)
        self.assertEqual(problems.current_problem_addresses()["count"], 2)  # default: severity dead

    # --- dates ---

    def test_dates_cover_the_whole_history_and_the_current_run(self):
        self.people = [person("p1", "a@x.example")]
        first = self.send("a@x.example", 100)
        self.bounce("a@x.example", 80)
        self.send("a@x.example", 60)  # fixed in the CRM and delivered
        started = self.bounce("a@x.example", 40)
        self.send("a@x.example", 20, SentEmail.DELIVERY_SUPPRESSED)
        last = self.send("a@x.example", 10, SentEmail.DELIVERY_SUPPRESSED)
        row = self.rows()["a@x.example"]
        for key, expected in (
            ("first_sent_at", first), ("first_problem_at", started), ("last_attempt_at", last),
        ):
            expected.refresh_from_db()
            self.assertEqual(row[key], expected.sent_at, key)
        self.assertEqual(row["attempts"], 6)

    # --- snapshot ---

    def test_twenty_is_read_once_per_snapshot_and_refresh_reads_again(self):
        self.people = [person("p1", "a@x.example")]
        self.bounce("a@x.example", 3)
        first = self.result()
        self.assertEqual(self.result()["snapshot_at"], first["snapshot_at"])
        self.assertEqual(self.fetch_people.call_count, 1)

        self.people = []  # removed in Twenty meanwhile
        self.assertEqual(self.result()["count"], 1)  # still the cached snapshot
        fresh = self.result(refresh=True)
        self.assertEqual(fresh["count"], 0)
        self.assertGreaterEqual(fresh["snapshot_at"], first["snapshot_at"])
        self.assertEqual(self.fetch_people.call_count, 2)
        self.assertEqual(self.result()["count"], 0)  # refresh replaced the cache

    def test_rows_are_ordered_dead_first_then_newest_attempt(self):
        self.people = [person(f"p{i}", f"a{i}@x.example") for i in range(3)]
        self.bounce("a0@x.example", 9, SentEmail.BOUNCE_MAILBOX_FULL)
        self.bounce("a1@x.example", 8)
        self.bounce("a2@x.example", 2)
        self.assertEqual(
            [row["address"] for row in self.result()["rows"]],
            ["a2@x.example", "a1@x.example", "a0@x.example"],
        )


@override_settings(CACHES=LOCMEM, TWENTY_API_URL="https://twenty.example")
class CurrentProblemsApiTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("operator"))
        patches = [
            patch("emails.services.problems.fetch_people", return_value=[person("p1", "gone@x.example")]),
            patch("emails.services.problems.fetch_companies", return_value=[company()]),
        ]
        self.fetch_people = patches[0].start()
        patches[1].start()
        for p in patches:
            self.addCleanup(p.stop)
        self.addCleanup(problems.cache.clear)
        SentEmail.objects.create(
            company_name="CPTS Val", company_email="gone@x.example", twenty_crm_id="crm-1", success=True,
            delivery_status=SentEmail.DELIVERY_BOUNCED, bounce_class=SentEmail.BOUNCE_MAILBOX_MISSING,
            delivery_detail="550 5.1.1 no",
        )

    def test_json_shape(self):
        body = self.client.get("/api/emails/current-problems").json()
        self.assertEqual(set(body), {"snapshot_at", "count", "rows"})
        self.assertEqual(body["count"], 1)
        self.assertEqual(set(body["rows"][0]), set(problems_fields()))

    def test_refresh_param_bypasses_the_cache(self):
        self.client.get("/api/emails/current-problems")
        self.client.get("/api/emails/current-problems")
        self.assertEqual(self.fetch_people.call_count, 1)
        self.client.get("/api/emails/current-problems", {"refresh": "true"})
        self.assertEqual(self.fetch_people.call_count, 2)

    def test_action_param_filters_json_and_csv(self):
        body = self.client.get("/api/emails/current-problems", {"action": "remove"}).json()
        self.assertEqual((body["count"], body["rows"][0]["action"], body["rows"][0]["reason"]), (1, "remove", "mailbox_unknown"))
        self.assertEqual(self.client.get("/api/emails/current-problems", {"action": "retry"}).json()["count"], 0)
        text = self.client.get("/api/emails/current-problems.csv", {"action": "retry"}).content.decode("utf-8-sig")
        self.assertEqual(len(text.strip().splitlines()), 1)  # header only
        self.assertEqual(self.client.get("/api/emails/current-problems", {"action": "delete"}).status_code, 422)

    def test_severity_is_validated(self):
        self.assertEqual(self.client.get("/api/emails/current-problems", {"severity": "all"}).status_code, 200)
        self.assertEqual(self.client.get("/api/emails/current-problems", {"severity": "nope"}).status_code, 422)

    def test_csv_has_a_bom_and_the_same_rows(self):
        response = self.client.get("/api/emails/current-problems.csv", {"severity": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(response.content.startswith("﻿".encode()))
        (row,) = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
        self.assertEqual(list(row), problems_fields())
        self.assertEqual(row["address"], "gone@x.example")
        self.assertEqual(row["where"], "person_primary")
        self.assertEqual(row["first_problem_at"], row["last_attempt_at"])

    def test_twenty_down_is_a_502(self):
        self.fetch_people.side_effect = httpx.ConnectError("down")
        self.assertEqual(self.client.get("/api/emails/current-problems").status_code, 502)
        self.assertEqual(self.client.get("/api/emails/current-problems.csv").status_code, 502)

    def test_login_is_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/emails/current-problems").status_code, 401)
        self.assertEqual(self.client.get("/api/emails/current-problems.csv").status_code, 401)

    def test_existing_export_gains_the_two_date_columns(self):
        response = self.client.get("/api/emails/problem-addresses.csv")
        (row,) = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
        self.assertTrue(row["first_sent_at"])
        self.assertEqual(row["first_problem_at"], row["first_sent_at"])
        body = self.client.get("/api/emails/problem-addresses").json()
        self.assertTrue(body[0]["first_sent_at"] and body[0]["first_problem_at"])


def problems_fields():
    from .api import CURRENT_PROBLEMS_CSV_COLUMNS
    return CURRENT_PROBLEMS_CSV_COLUMNS


@override_settings(TWENTY_API_URL="https://twenty.example", TWENTY_API_KEY="k")
class FetchPeopleTests(TestCase):
    def page(self, people, next_cursor=None):
        response = MagicMock()
        response.json.return_value = {
            "data": {"people": people},
            "pageInfo": {"hasNextPage": bool(next_cursor), "endCursor": next_cursor},
        }
        return response

    @patch("emails.services.twenty_crm.httpx.Client")
    def test_pages_are_followed_and_every_address_is_kept(self, mock_client):
        get = mock_client.return_value.__enter__.return_value.get
        get.side_effect = [
            self.page([{
                "id": "p1", "name": {"firstName": "Ada", "lastName": "Martin"}, "jobTitle": "Trésorier",
                "emails": {"primaryEmail": "a@x.example", "additionalEmails": ["b@x.example", None]},
                "companyId": "co-1", "company": {"id": "co-1", "name": "CPTS Val", "companyType": "CPTS"},
            }], next_cursor="c1"),
            self.page([{"id": "p2", "name": None, "emails": None, "company": None}]),
        ]
        people = fetch_people()
        self.assertEqual(get.call_args_list[1].kwargs["params"]["starting_after"], "c1")
        self.assertEqual(get.call_args_list[0].args[0], "https://twenty.example/rest/people")
        self.assertEqual(people[0], {
            "id": "p1", "name": "Ada Martin", "job_title": "Trésorier", "primary_email": "a@x.example",
            "additional_emails": ["b@x.example"], "company_id": "co-1", "company_name": "CPTS Val",
            "company_type": "CPTS",
        })
        self.assertEqual(
            (people[1]["primary_email"], people[1]["additional_emails"], people[1]["company_id"]),
            ("", [], ""),
        )


class CreateApiTokenCommandTests(TestCase):
    def run_command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command("create_api_token", *args, stdout=out, stderr=err)
        return out.getvalue().strip(), err.getvalue()

    def test_prints_the_token_once_on_stdout_only(self):
        token, message = self.run_command("--name", "claude-prospection")
        self.assertGreaterEqual(len(token), 40)
        self.assertNotIn(token, message)
        self.assertEqual(ApiToken.objects.get().sha256, hash_token(token))
        self.assertIsNotNone(find_token(token))

    def test_a_name_is_used_once(self):
        self.run_command("--name", "claude-prospection")
        with self.assertRaises(CommandError):
            self.run_command("--name", "claude-prospection")
        with self.assertRaises(CommandError):
            self.run_command("--name", "  ")


class MailgunSuppressionTests(TestCase):
    LISTED = "Mon, 16 Mar 2026 15:45:15 UTC"

    def test_a_bounce_item_is_classified_and_refreshed_in_place(self):
        item = {"address": " Gone@X.example ", "code": "550", "error": "5.1.1 Unknown recipient", "created_at": self.LISTED}
        row = record_list_item("bounce", item)
        self.assertEqual(
            (row.address, row.code, row.enhanced_code, row.bounce_class),
            ("gone@x.example", "550", "5.1.1", "mailbox_missing"),
        )
        self.assertEqual(row.listed_at.isoformat(), "2026-03-16T15:45:15+00:00")

        record_list_item("bounce", {**item, "error": "5.2.2 Mailbox full"})
        (row,) = MailgunSuppression.objects.all()
        self.assertEqual(row.bounce_class, "mailbox_full")

    def test_bounce_and_complaint_lists_are_kept_apart(self):
        record_list_item("bounce", {"address": "a@x.example", "code": "550", "error": "5.1.1 no", "created_at": self.LISTED})
        row = record_list_item("complaint", {"address": "a@x.example", "created_at": self.LISTED})
        self.assertEqual((row.bounce_class, row.code), ("", ""))
        self.assertEqual(MailgunSuppression.objects.count(), 2)

    def test_backfill_stores_every_list_entry_even_for_addresses_we_never_mailed(self):
        pages = {
            "bounces": [{"address": "stranger@x.example", "code": "550", "error": "5.1.1 no", "created_at": self.LISTED}],
            "complaints": [{"address": "angry@x.example", "created_at": self.LISTED}],
        }

        def fake_paginate(http, url, params=None):
            return iter(pages.get(url.rsplit("/", 1)[1], []))

        out = io.StringIO()
        with patch("emails.management.commands.backfill_mailgun_events.paginate", fake_paginate):
            call_command("backfill_mailgun_events", "--skip-events", stdout=out)
            call_command("backfill_mailgun_events", "--skip-events", stdout=out)
        self.assertIn("unmatched 2", out.getvalue())
        self.assertIn("suppression entries stored 2", out.getvalue())
        self.assertEqual(
            sorted(MailgunSuppression.objects.values_list("address", "kind")),
            [("angry@x.example", "complaint"), ("stranger@x.example", "bounce")],
        )

    def test_the_old_csv_export_explains_a_suppression_too(self):
        SentEmail.objects.create(
            company_name="CPTS", company_email="a@x.example", twenty_crm_id="crm-1", success=True,
            delivery_status=SentEmail.DELIVERY_SUPPRESSED,
        )
        record_list_item("bounce", {"address": "a@x.example", "code": "550", "error": "5.1.1 no", "created_at": self.LISTED})
        from .services.delivery import problem_addresses
        (row,) = problem_addresses()
        self.assertEqual((row["bounce_class"], row["delivery_detail"]), ("mailbox_missing", "550 5.1.1 no"))


class AdviseTests(TestCase):
    def test_closed_account_codes_are_told_from_an_unknown_mailbox(self):
        for detail in ("550 5.2.1 This mailbox has been blocked due to inactivity", "525 5.7.13 Disabled recipient address"):
            self.assertEqual(advise("bounced", "mailbox_missing", detail), ("remove", "account_closed"), detail)
        self.assertEqual(advise("bounced", "mailbox_missing", "550 5.1.1 User unknown"), ("remove", "mailbox_unknown"))

    def test_nothing_that_can_heal_or_is_unproven_says_remove(self):
        self.assertEqual(advise("complained", "", ""), ("review", "spam_complaint"))
        self.assertEqual(advise("suppressed", "", "Spam complaint listed by Mailgun on 2030-01-01"), ("review", "spam_complaint"))
        self.assertEqual(advise("suppressed", "", problems.UNKNOWN_SUPPRESSION), ("review", "suppressed_unknown"))
        self.assertEqual(advise("bounced", "other", "612 unable to connect to MX servers: x"), ("review", "server_unreachable"))
        self.assertEqual(advise("bounced", "other", "554 transaction failed"), ("review", "other"))


class ReclassifyBouncesTests(TestCase):
    def make(self, detail, bounce_class):
        return SentEmail.objects.create(
            company_name="x", company_email="a@x.example", twenty_crm_id="c", success=True,
            delivery_status=SentEmail.DELIVERY_BOUNCED, bounce_class=bounce_class, delivery_detail=detail,
        )

    def run_command(self, *args):
        out = io.StringIO()
        call_command("reclassify_bounces", *args, stdout=out)
        return out.getvalue()

    def test_report_only_by_default_then_apply(self):
        old = self.make("525 5.7.13 Disabled recipient address", "blocked")
        same = self.make("550 5.1.1 User unknown", "mailbox_missing")
        MailgunSuppression.objects.create(
            address="a@x.example", kind="bounce", code="550", listed_at=timezone.now(),
            error="5.4.1 Recipient address rejected: Access denied", bounce_class="other",
        )
        report = self.run_command()
        self.assertIn("sent email: blocked -> mailbox_missing: 1", report)
        self.assertIn("mailgun list: other -> mailbox_missing: 1", report)
        self.assertIn("Would change 2", report)
        old.refresh_from_db()
        self.assertEqual(old.bounce_class, "blocked")

        self.assertIn("Changed 2", self.run_command("--apply"))
        old.refresh_from_db(); same.refresh_from_db()
        self.assertEqual((old.bounce_class, same.bounce_class), ("mailbox_missing", "mailbox_missing"))
        self.assertEqual(MailgunSuppression.objects.get().bounce_class, "mailbox_missing")
        self.assertIn("Changed 0", self.run_command("--apply"))
