import httpx
from django.conf import settings


def fetch_companies() -> list[dict]:
    """Fetch all companies from Twenty CRM via REST API."""
    companies = []
    cursor = None
    headers = {
        "Authorization": f"Bearer {settings.TWENTY_API_KEY}",
    }

    with httpx.Client(timeout=60) as client:
        while True:
            params = {"limit": 50, "depth": 1}
            if cursor:
                params["starting_after"] = cursor

            response = client.get(
                f"{settings.TWENTY_API_URL}/rest/companies",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()

            data = body.get("data", {}).get("companies", [])
            page_info = body.get("pageInfo", {})

            for company in data:
                email_data = company.get("email") or {}
                emails = []
                primary = email_data.get("primaryEmail", "")
                if primary:
                    emails.append(primary)
                for extra in email_data.get("additionalEmails", None) or []:
                    if extra and extra not in emails:
                        emails.append(extra)

                companies.append({
                    "id": company["id"],
                    "name": company.get("name", ""),
                    "emails": emails,
                    "company_type": company.get("companyType"),
                    "domain": (company.get("domainName") or {}).get("primaryLinkUrl", ""),
                    "city": (company.get("address") or {}).get("addressCity", ""),
                    "created_at": company.get("createdAt", ""),
                    "people": [
                        {
                            "id": p.get("id", ""),
                            "name": f"{(p.get('name') or {}).get('firstName', '')} {(p.get('name') or {}).get('lastName', '')}".strip(),
                            "email": (p.get('emails') or {}).get('primaryEmail', ''),
                            "created_at": p.get("createdAt", ""),
                        }
                        for p in (company.get("people") or [])
                    ],
                })

            if not page_info.get("hasNextPage", False):
                break
            cursor = page_info.get("endCursor")

    return companies


def fetch_people() -> list[dict]:
    """Fetch every person from Twenty CRM with all their addresses and their company.

    Unlike the people nested in fetch_companies(), this keeps additionalEmails.
    """
    people = []
    cursor = None
    headers = {
        "Authorization": f"Bearer {settings.TWENTY_API_KEY}",
    }

    with httpx.Client(timeout=60) as client:
        while True:
            params = {"limit": 50, "depth": 1}
            if cursor:
                params["starting_after"] = cursor

            response = client.get(
                f"{settings.TWENTY_API_URL}/rest/people",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()

            data = body.get("data", {}).get("people", [])
            page_info = body.get("pageInfo", {})

            for person in data:
                email_data = person.get("emails") or {}
                name = person.get("name") or {}
                company = person.get("company") or {}
                people.append({
                    "id": person["id"],
                    "name": f"{name.get('firstName') or ''} {name.get('lastName') or ''}".strip(),
                    "job_title": person.get("jobTitle") or "",
                    "primary_email": email_data.get("primaryEmail") or "",
                    "additional_emails": [
                        extra for extra in email_data.get("additionalEmails") or [] if extra
                    ],
                    "company_id": person.get("companyId") or company.get("id") or "",
                    "company_name": company.get("name") or "",
                    "company_type": company.get("companyType"),
                })

            if not page_info.get("hasNextPage", False):
                break
            cursor = page_info.get("endCursor")

    return people
