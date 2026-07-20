"""Twenty CRM interactions for the web-prospects feature.

Reuses the same REST API and credentials as the CSV importer. Adds creation of
linked people (coordinators, team leaders, a contact person) and a note holding
the Finess metadata, targeted at the newly created company.
"""
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# companyType is a SELECT custom field in Twenty; the option value for MSP is
# the uppercase "MSP" (== CompanyType.label, NOT the lowercase .name).
MSP_COMPANY_TYPE_VALUE = "MSP"


def _headers(json: bool = False) -> dict:
    h = {"Authorization": f"Bearer {settings.TWENTY_API_KEY}"}
    if json:
        h["Content-Type"] = "application/json"
    return h


def _base() -> str:
    return settings.TWENTY_API_URL.rstrip("/")


def find_companies_by_name(name: str) -> list[dict]:
    """Return all Twenty companies whose name matches (case-insensitive)."""
    response = httpx.get(
        f"{_base()}/rest/companies",
        headers=_headers(),
        params={"filter": f'name[ilike]:"{name}"'},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("companies", [])


def find_probable_duplicates(record: dict) -> list[dict]:
    """Ask Twenty for probable duplicate companies of a scraped record.

    Uses Twenty's own duplicate detection (POST /rest/companies/duplicates),
    which matches on exact name and domain. Complements our name[ilike] check
    by catching same-domain companies under a different name.

    Returns a list of {"id", "name", "domain"} for matched companies.
    """
    data: dict = {"name": record.get("name", "")}
    website = record.get("website", "")
    if website:
        data["domainName"] = {"primaryLinkUrl": website}
    try:
        resp = httpx.post(
            f"{_base()}/rest/companies/duplicates",
            headers=_headers(json=True), json={"data": [data]}, timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    out = []
    for block in resp.json().get("data", []):
        for c in block.get("companyDuplicates", []):
            out.append({
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "domain": (c.get("domainName") or {}).get("primaryLinkUrl", ""),
            })
    return out


def create_company(record: dict, company_type_value: str | None) -> dict:
    """Create a company in Twenty from a scraped record. Returns the company dict."""
    body: dict = {
        "name": record.get("name", ""),
        "address": {
            "addressStreet1": record.get("address_line1", ""),
            "addressPostcode": record.get("postcode", ""),
            "addressCity": record.get("city", ""),
            "addressCountry": "France",
        },
    }
    website = record.get("website", "")
    if website:
        body["domainName"] = {"primaryLinkUrl": website}
    # NOTE: email is intentionally NOT set on the company. In Twenty, exchanged
    # emails only surface when the address is on a Person, so the address lives
    # on the "Contact" person instead (see create_person calls in process_record).
    if company_type_value:
        body["companyType"] = company_type_value

    response = httpx.post(
        f"{_base()}/rest/companies", headers=_headers(json=True), json=body, timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("createCompany", {})


def create_person(
    first_name: str,
    last_name: str,
    company_id: str,
    job_title: str = "",
    email: str = "",
    phone: str = "",
) -> dict:
    """Create a person in Twenty linked to a company."""
    body: dict = {
        "name": {"firstName": first_name, "lastName": last_name},
        "companyId": company_id,
    }
    if job_title:
        body["jobTitle"] = job_title
    if email:
        body["emails"] = {"primaryEmail": email}
    if phone:
        body["phones"] = {
            "primaryPhoneNumber": phone,
            "primaryPhoneCallingCode": "+33",
            "primaryPhoneCountryCode": "FR",
        }
    response = httpx.post(
        f"{_base()}/rest/people", headers=_headers(json=True), json=body, timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("createPerson", {})


def fetch_company(company_id: str) -> dict:
    """Fetch a single company by id (depth=1)."""
    resp = httpx.get(
        f"{_base()}/rest/companies/{company_id}",
        headers=_headers(), params={"depth": 1}, timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("company", {})


def fetch_company_people(company_id: str) -> list[dict]:
    """Return the people related to a company."""
    resp = httpx.get(
        f"{_base()}/rest/people",
        headers=_headers(),
        params={"filter": f'companyId[eq]:"{company_id}"', "depth": 1},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("people", [])


def _person_has_email(person: dict) -> bool:
    return bool((person.get("emails") or {}).get("primaryEmail"))


def _person_has_phone(person: dict) -> bool:
    return bool((person.get("phones") or {}).get("primaryPhoneNumber"))


def compute_missing(company: dict, people: list[dict], record: dict) -> list[dict]:
    """Compute which essential fields are missing on an existing Twenty MSP.

    Returns a list of diff entries, each:
        {"field", "label", "value", "target"}
        target: "company" | "contact_person"

    Only fields where the scraped record HAS a value and the existing record
    LACKS it are returned. Targets:
      - email  → a "Contact" person (Twenty only surfaces exchanged emails
                 when the address is on a Person; see memory note). Missing
                 unless a related person already has an email.
      - phone  → a "Contact" person (Twenty's Company has no phone field).
                 Missing unless a related person already has a phone.
      - domain → the company record.
      - address→ the company record (missing if any part empty).
    """
    diff: list[dict] = []

    # email → Contact person; satisfied only if a related person already has one.
    scraped_email = record.get("email", "")
    if scraped_email and not any(_person_has_email(p) for p in people):
        diff.append({
            "field": "email", "label": "Email",
            "value": scraped_email, "target": "contact_person",
        })

    # phone → Contact person; satisfied only if a related person already has one.
    scraped_phone = record.get("phone", "")
    if scraped_phone and not any(_person_has_phone(p) for p in people):
        diff.append({
            "field": "phone", "label": "Phone",
            "value": scraped_phone, "target": "contact_person",
        })

    # domain → company record.
    scraped_domain = record.get("website", "")
    company_domain = (company.get("domainName") or {}).get("primaryLinkUrl", "")
    if scraped_domain and not company_domain:
        diff.append({
            "field": "domain", "label": "Domain name",
            "value": scraped_domain, "target": "company",
        })

    # address → company record; missing if any part is empty.
    addr = company.get("address") or {}
    has_addr = bool(
        addr.get("addressStreet1") or addr.get("addressPostcode") or addr.get("addressCity")
    )
    scraped_addr = {
        "address_line1": record.get("address_line1", ""),
        "postcode": record.get("postcode", ""),
        "city": record.get("city", ""),
    }
    if not has_addr and any(scraped_addr.values()):
        parts = [scraped_addr["address_line1"], f'{scraped_addr["postcode"]} {scraped_addr["city"]}'.strip()]
        diff.append({
            "field": "address", "label": "Address",
            "value": ", ".join(p for p in parts if p),
            "target": "company",
            "_address": scraped_addr,
        })

    return diff


def apply_update(company: dict, diff: list[dict], record: dict) -> dict:
    """Apply the computed diff to an existing Twenty MSP.

    - domain / address → PATCH the company (only the missing fields).
    - email / phone    → a "Contact" person carrying them, linked to the company.
      (Twenty's Company has no phone field, and emails must be on a Person to
      surface threads — see memory note.) One Contact person carries both.
    Returns a summary of what was updated.
    """
    company_id = company["id"]
    updated_fields: list[str] = []
    fields = {d["field"]: d for d in diff}

    # --- Company patch (domain, address) ---
    company_patch: dict = {}
    if "domain" in fields:
        company_patch["domainName"] = {"primaryLinkUrl": fields["domain"]["value"]}
        updated_fields.append("domain")
    if "address" in fields:
        a = fields["address"]["_address"]
        company_patch["address"] = {
            "addressStreet1": a["address_line1"],
            "addressPostcode": a["postcode"],
            "addressCity": a["city"],
            "addressCountry": "France",
        }
        updated_fields.append("address")
    if company_patch:
        resp = httpx.patch(
            f"{_base()}/rest/companies/{company_id}",
            headers=_headers(json=True), json=company_patch, timeout=30,
        )
        resp.raise_for_status()

    # --- Email / phone → a Contact person (one person carries both) ---
    # Duplicate email/phone (already on another company) is non-fatal: skip that
    # field so the rest of the update still lands.
    person_id = ""
    skipped: list[str] = []
    if "email" in fields or "phone" in fields:
        res = create_contact_person_safe(
            company_id, record.get("name", ""),
            fields["email"]["value"] if "email" in fields else "",
            fields["phone"]["value"] if "phone" in fields else "",
        )
        person_id = res["person_id"]
        skipped = res["skipped"]
        duplicate_owner = res.get("duplicate_owner")
        if "email" in fields and "email" not in skipped:
            updated_fields.append("email")
        if "phone" in fields and "phone" not in skipped:
            updated_fields.append("phone")
    else:
        duplicate_owner = None

    return {
        "updated_fields": updated_fields, "person_id": person_id,
        "skipped": skipped, "duplicate_owner": duplicate_owner,
    }


def _is_duplicate_error(exc: httpx.HTTPStatusError) -> bool:
    """True if Twenty rejected a write because a unique value already exists."""
    if exc.response.status_code != 400:
        return False
    return "duplicate" in exc.response.text.lower()


def find_person_owner_by_email(email: str) -> dict | None:
    """Return {"company_name", "company_id"} of the company owning a person with
    this email, or None. Used to explain an email-duplicate collision."""
    if not email:
        return None
    try:
        resp = httpx.get(
            f"{_base()}/rest/people",
            headers=_headers(),
            params={"filter": f'emails.primaryEmail[eq]:"{email}"', "depth": 1},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    for p in resp.json().get("data", {}).get("people", []):
        company = p.get("company") or {}
        if company.get("id"):
            return {"company_name": company.get("name", ""), "company_id": company["id"]}
    return None


def create_contact_person_safe(
    company_id: str, company_name: str, email: str, phone: str,
) -> dict:
    """Create a Contact person, tolerating Twenty's unique email duplicates.

    Twenty enforces uniqueness on email; the same address can already exist on
    another company (e.g. a shared coordinator, or the same org under a different
    name). Rather than failing the whole record, retry without the offending
    field so the rest still lands, and record which company owns the duplicate.

    Returns {"person_id", "skipped": [fields dropped], "duplicate_owner": {..}|None}.
    """
    skipped: list[str] = []
    duplicate_owner = None
    cur_email, cur_phone = email, phone

    for _ in range(3):
        if not (cur_email or cur_phone):
            return {"person_id": "", "skipped": skipped, "duplicate_owner": duplicate_owner}
        try:
            person = create_person(
                first_name="Contact", last_name=company_name,
                company_id=company_id, job_title="Contact",
                email=cur_email, phone=cur_phone,
            )
            return {
                "person_id": person.get("id", ""),
                "skipped": skipped,
                "duplicate_owner": duplicate_owner,
            }
        except httpx.HTTPStatusError as e:
            if not _is_duplicate_error(e):
                raise
            # Drop the offender and retry. Email is the unique field; record the
            # company that already owns it, then fall back to phone only.
            if cur_email:
                if duplicate_owner is None:
                    duplicate_owner = find_person_owner_by_email(cur_email)
                skipped.append("email")
                cur_email = ""
            elif cur_phone:
                skipped.append("phone")
                cur_phone = ""
            else:
                return {"person_id": "", "skipped": skipped, "duplicate_owner": duplicate_owner}
    return {"person_id": "", "skipped": skipped, "duplicate_owner": duplicate_owner}


def create_note_for_company(company_id: str, title: str, body_text: str) -> dict:
    """Create a note and target it at a company."""
    note_resp = httpx.post(
        f"{_base()}/rest/notes",
        headers=_headers(json=True),
        json={"title": title, "bodyV2": {"markdown": body_text}},
        timeout=30,
    )
    note_resp.raise_for_status()
    note = note_resp.json().get("data", {}).get("createNote", {})
    note_id = note.get("id")

    if note_id:
        target_resp = httpx.post(
            f"{_base()}/rest/noteTargets",
            headers=_headers(json=True),
            json={"noteId": note_id, "targetCompanyId": company_id},
            timeout=30,
        )
        target_resp.raise_for_status()
    return note


def _finess_note_body(record: dict) -> str:
    lines = []
    if record.get("finess_number"):
        lines.append(f"**Numéro Finess :** {record['finess_number']}")
    if record.get("finess_date"):
        lines.append(f"**Date d'enregistrement Finess :** {record['finess_date']}")
    if record.get("project_type"):
        lines.append(f"**Type de projet :** {record['project_type']}")
    return "\n\n".join(lines)


def process_record(record: dict, company_type_value: str | None) -> dict:
    """Create one MSP (company + people + note) in Twenty.

    Returns {status, twenty_company_id, missing_fields, error}. Assumes the
    caller has already handled idempotency (existence checks).
    """
    missing_fields = _missing_fields(record)
    try:
        company = create_company(record, company_type_value)
        company_id = company.get("id", "")

        # Coordinators
        for person in record.get("coordinators", []):
            _safe_person(person, company_id, "Coordinateur")
        # Team leaders
        for person in record.get("team_leaders", []):
            _safe_person(person, company_id, "Team Leader")
        # Contact person carrying the entite-contact email/phone. Duplicate
        # email/phone (already on another company) is non-fatal — skip that field.
        warnings: list[str] = []
        duplicate_owner = None
        if record.get("email") or record.get("phone"):
            res = create_contact_person_safe(
                company_id, record.get("name", ""),
                record.get("email", ""), record.get("phone", ""),
            )
            if res["skipped"]:
                warnings.append(
                    f"Contact {'/'.join(res['skipped'])} already exists elsewhere in Twenty (skipped)"
                )
                duplicate_owner = res.get("duplicate_owner")
        # Finess note. Non-fatal: the company + people are the important parts,
        # so a note failure is recorded as a warning rather than failing the record.
        note_body = _finess_note_body(record)
        if note_body:
            try:
                create_note_for_company(company_id, "Informations Finess", note_body)
            except httpx.HTTPStatusError as e:
                warnings.append(f"Note not created: {e.response.text[:200]}")
            except Exception as e:  # noqa: BLE001
                warnings.append(f"Note not created: {str(e)[:200]}")

        return {
            "status": "created",
            "twenty_company_id": company_id,
            "missing_fields": missing_fields,
            "error": "; ".join(warnings),
            "duplicate_owner": duplicate_owner,
        }
    except httpx.HTTPStatusError as e:
        return {
            "status": "failed",
            "twenty_company_id": "",
            "missing_fields": missing_fields,
            "error": e.response.text[:500],
            "duplicate_owner": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "failed",
            "twenty_company_id": "",
            "missing_fields": missing_fields,
            "error": str(e)[:500],
            "duplicate_owner": None,
        }


def _safe_person(person: dict, company_id: str, job_title: str):
    first = person.get("first_name", "")
    last = person.get("last_name", "")
    if not (first or last):
        return
    create_person(first, last, company_id, job_title=job_title)


def _missing_fields(record: dict) -> list[str]:
    """Report which expected fields are empty on the scraped record."""
    checks = {
        "name": record.get("name"),
        "address_line1": record.get("address_line1"),
        "postcode": record.get("postcode"),
        "city": record.get("city"),
        "email": record.get("email"),
        "phone": record.get("phone"),
        "website": record.get("website"),
        "finess_number": record.get("finess_number"),
    }
    return [k for k, v in checks.items() if not v]
