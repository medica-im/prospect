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
        # Contact person carrying the entite-contact email/phone
        if record.get("email") or record.get("phone"):
            create_person(
                first_name="Contact",
                last_name=record.get("name", ""),
                company_id=company_id,
                job_title="Contact",
                email=record.get("email", ""),
                phone=record.get("phone", ""),
            )
        # Finess note. Non-fatal: the company + people are the important parts,
        # so a note failure is recorded as a warning rather than failing the record.
        note_error = ""
        note_body = _finess_note_body(record)
        if note_body:
            try:
                create_note_for_company(company_id, "Informations Finess", note_body)
            except httpx.HTTPStatusError as e:
                note_error = f"Note not created: {e.response.text[:300]}"
            except Exception as e:  # noqa: BLE001
                note_error = f"Note not created: {str(e)[:300]}"

        return {
            "status": "created",
            "twenty_company_id": company_id,
            "missing_fields": missing_fields,
            "error": note_error,
        }
    except httpx.HTTPStatusError as e:
        return {
            "status": "failed",
            "twenty_company_id": "",
            "missing_fields": missing_fields,
            "error": e.response.text[:500],
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "failed",
            "twenty_company_id": "",
            "missing_fields": missing_fields,
            "error": str(e)[:500],
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
