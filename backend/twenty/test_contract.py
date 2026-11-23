"""Opt-in contract test: prospect's Twenty write calls against a real, dev Twenty.

Skipped unless TWENTY_CONTRACT_URL and TWENTY_CONTRACT_KEY are set. Run it
before upgrading production Twenty, against a restored copy of production:

    TWENTY_CONTRACT_URL=http://127.0.0.1:3001 TWENTY_CONTRACT_KEY=... \
        python manage.py test twenty.test_contract

It writes records named ZZ-contract-test-P<run id> and deletes them in tearDown.
It refuses any host other than 127.0.0.1, localhost or dev.twenty.medica.im, so
it can never write to production.
"""
import os
import unittest
import uuid
from urllib.parse import urlparse

import httpx
from django.test import SimpleTestCase, override_settings

from twenty import services as twenty_services
from webprospects import services as wp

CONTRACT_URL = os.environ.get("TWENTY_CONTRACT_URL", "").rstrip("/")
CONTRACT_KEY = os.environ.get("TWENTY_CONTRACT_KEY", "")
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "dev.twenty.medica.im"}


@unittest.skipUnless(
    CONTRACT_URL and CONTRACT_KEY,
    "set TWENTY_CONTRACT_URL and TWENTY_CONTRACT_KEY to run against a dev Twenty",
)
class TwentyContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        host = urlparse(CONTRACT_URL).hostname
        if host not in ALLOWED_HOSTS:
            raise RuntimeError(
                f"TWENTY_CONTRACT_URL host {host!r} refused: the contract test only "
                f"writes to {sorted(ALLOWED_HOSTS)}"
            )
        super().setUpClass()
        cls._override = override_settings(
            TWENTY_API_URL=CONTRACT_URL, TWENTY_API_KEY=CONTRACT_KEY,
        )
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        super().tearDownClass()

    def setUp(self):
        self.run_id = uuid.uuid4().hex[:8]
        self.prefix = f"ZZ-contract-test-P{self.run_id}"
        self.headers = {"Authorization": f"Bearer {CONTRACT_KEY}"}

    def tearDown(self):
        # Everything this run created has the run id in its company name; the
        # people, notes and note targets hang off those companies.
        for company in self._get("/rest/companies", filter=f'name[like]:"%{self.run_id}%"', limit=200)[
            "data"
        ]["companies"]:
            cid = company["id"]
            targets = self._get(
                "/rest/noteTargets", filter=f'targetCompanyId[eq]:"{cid}"', depth=1,
            )["data"]["noteTargets"]
            for target in targets:
                self._delete("noteTargets", target["id"])
                if target.get("note"):
                    self._delete("notes", target["note"]["id"])
            for person in wp.fetch_company_people(cid):
                self._delete("people", person["id"])
            self._delete("companies", cid)

    # --- helpers ---

    def _get(self, path, **params):
        resp = httpx.get(f"{CONTRACT_URL}{path}", headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, kind, record_id):
        resp = httpx.delete(f"{CONTRACT_URL}/rest/{kind}/{record_id}", headers=self.headers, timeout=30)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    @staticmethod
    def _bare(url):
        # Twenty stores domains without the scheme.
        return url.split("://", 1)[-1]

    def _record(self, n, **extra):
        slug = f"zz-contract-test-p{n}-{self.run_id}"
        record = {
            "name": f"{self.prefix}-{n} MSP",
            "address_line1": f"{n} rue du Test", "postcode": "84000", "city": "Avignon",
            "email": f"{slug}@example.invalid", "phone": "0490123456",
            "website": f"https://{slug}.example.invalid",
        }
        record.update(extra)
        return record

    # --- tests ---

    def test_create_company(self):
        record = self._record(1)
        company = wp.create_company(record, "MSP")
        self.assertTrue(company["id"])  # data.createCompany
        got = wp.fetch_company(company["id"])
        self.assertEqual(got["companyType"], "MSP")
        self.assertEqual(got["domainName"]["primaryLinkUrl"], self._bare(record["website"]))
        self.assertEqual(
            {k: got["address"][k] for k in (
                "addressStreet1", "addressPostcode", "addressCity", "addressCountry")},
            {"addressStreet1": "1 rue du Test", "addressPostcode": "84000",
             "addressCity": "Avignon", "addressCountry": "France"},
        )

    def test_create_person_and_find_owner(self):
        record = self._record(2)
        company = wp.create_company(record, "MSP")
        person = wp.create_person(
            "Alice", "Durand", company["id"], job_title="Coordinateur",
            email=record["email"], phone=record["phone"],
        )
        self.assertTrue(person["id"])  # data.createPerson
        (stored,) = wp.fetch_company_people(company["id"])
        self.assertEqual(stored["emails"]["primaryEmail"], record["email"])
        self.assertEqual(stored["jobTitle"], "Coordinateur")
        self.assertEqual(stored["phones"]["primaryPhoneCallingCode"], "+33")
        self.assertEqual(stored["phones"]["primaryPhoneCountryCode"], "FR")
        # Twenty normalises the number: the leading trunk 0 is dropped.
        self.assertEqual(stored["phones"]["primaryPhoneNumber"], "490123456")
        owner = wp.find_person_owner_by_email(record["email"])
        self.assertEqual(owner["company_id"], company["id"])

    def test_contact_person_duplicate_email_is_skipped(self):
        record = self._record(3)
        owner = wp.create_company(record, "MSP")
        wp.create_person("Alice", "Durand", owner["id"], email=record["email"])
        other = wp.create_company({"name": f"{self.prefix}-3b MSP"}, "MSP")
        result = wp.create_contact_person_safe(other["id"], record["email"], "0490123457")
        self.assertEqual(result["skipped"], ["email"])
        self.assertEqual(result["duplicate_owner"]["company_id"], owner["id"])
        (contact,) = wp.fetch_company_people(other["id"])
        self.assertEqual(contact["name"]["firstName"], "Contact")
        self.assertFalse(contact["name"]["lastName"])
        self.assertEqual(contact["phones"]["primaryPhoneNumber"], "490123457")

    def test_create_note_for_company(self):
        company = wp.create_company(self._record(4), "MSP")
        note = wp.create_note_for_company(company["id"], "Informations Finess", "**Numéro Finess :** 840000004")
        self.assertTrue(note["id"])  # data.createNote
        (target,) = self._get(
            "/rest/noteTargets", filter=f'noteId[eq]:"{note["id"]}"',
        )["data"]["noteTargets"]
        self.assertEqual(target["targetCompanyId"], company["id"])
        stored = self._get(f"/rest/notes/{note['id']}")["data"]["note"]
        self.assertIn("840000004", stored["bodyV2"]["markdown"])

    def test_compute_missing_and_apply_update(self):
        record = self._record(5)
        company = wp.create_company({"name": record["name"]}, "MSP")  # no domain, empty address
        company = wp.fetch_company(company["id"])
        people = wp.fetch_company_people(company["id"])
        diff = wp.compute_missing(company, people, record)
        self.assertEqual(sorted(d["field"] for d in diff), ["address", "domain", "email", "phone"])
        result = wp.apply_update(company, diff, record)
        self.assertEqual(sorted(result["updated_fields"]), ["address", "domain", "email", "phone"])
        self.assertTrue(result["person_id"])
        after = wp.fetch_company(company["id"])
        self.assertEqual(after["domainName"]["primaryLinkUrl"], self._bare(record["website"]))
        self.assertEqual(after["address"]["addressStreet1"], "5 rue du Test")
        self.assertEqual(after["address"]["addressCountry"], "France")
        self.assertEqual(wp.compute_missing(after, wp.fetch_company_people(company["id"]), record), [])

    def test_process_record(self):
        record = self._record(
            6,
            coordinators=[{"first_name": "Bob", "last_name": "Martin"}],
            team_leaders=[{"first_name": "Claire", "last_name": "Petit"}],
            finess_number="840000006", finess_date="2025-01-15", project_type="MSP",
        )
        result = wp.process_record(record, "MSP")
        self.assertEqual((result["status"], result["error"]), ("created", ""))
        self.assertEqual(result["missing_fields"], [])
        cid = result["twenty_company_id"]
        people = sorted(
            (p["name"]["firstName"], p["jobTitle"]) for p in wp.fetch_company_people(cid)
        )
        self.assertEqual(
            people, [("Bob", "Coordinateur"), ("Claire", "Gérant"), ("Contact", "")],
        )
        (target,) = self._get(
            "/rest/noteTargets", filter=f'targetCompanyId[eq]:"{cid}"', depth=1,
        )["data"]["noteTargets"]
        self.assertIn("840000006", target["note"]["bodyV2"]["markdown"])

        # A second record reusing the contact email still lands, with a warning.
        again = wp.process_record(
            self._record(7, email=record["email"], phone="0490123458"), "MSP",
        )
        self.assertEqual(again["status"], "created")
        self.assertIn("already exists", again["error"])
        self.assertEqual(again["duplicate_owner"]["company_id"], cid)

    def test_duplicate_and_name_lookups(self):
        record = self._record(8)
        company = wp.create_company(record, "MSP")
        by_name = wp.find_probable_duplicates({"name": record["name"]})
        by_domain = wp.find_probable_duplicates(
            {"name": f"{self.prefix}-8-other", "website": record["website"]},
        )
        for found in (by_name, by_domain):
            self.assertIn(company["id"], [d["id"] for d in found])
            self.assertTrue(all(set(d) == {"id", "name", "domain"} for d in found))
        self.assertEqual(wp.find_probable_duplicates({"name": f"{self.prefix}-nothing"}), [])
        self.assertEqual([c["id"] for c in wp.find_companies_by_name(record["name"])], [company["id"]])
        self.assertEqual(twenty_services.find_company_by_name(record["name"].lower())["id"], company["id"])
        self.assertIsNone(twenty_services.find_company_by_name(f"{self.prefix}-nothing"))

    def test_create_company_in_twenty(self):
        slug = f"zz-contract-test-p9-{self.run_id}"
        body = twenty_services.create_company_in_twenty(
            {"name": f"{self.prefix}-9 CPTS", "email": f"{slug}@example.invalid",
             "domain": f"https://{slug}.example.invalid", "postcode": "84"},
            "MSP",
        )
        company = body["data"]["createCompany"]
        got = wp.fetch_company(company["id"])
        self.assertEqual(got["email"]["primaryEmail"], f"{slug}@example.invalid")
        self.assertEqual(got["address"]["addressPostcode"], "84")
        self.assertEqual(got["companyType"], "MSP")
