import httpx
from django.conf import settings


def fetch_companies() -> list[dict]:
    """Fetch all companies from Twenty CRM via REST API."""
    companies = []
    cursor = None
    headers = {
        "Authorization": f"Bearer {settings.TWENTY_API_KEY}",
    }

    with httpx.Client() as client:
        while True:
            params = {"limit": 50}
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
                companies.append({
                    "id": company["id"],
                    "name": company.get("name", ""),
                    "email": email_data.get("primaryEmail", ""),
                    "company_type": company.get("companyType"),
                    "domain": (company.get("domainName") or {}).get("primaryLinkUrl", ""),
                    "city": (company.get("address") or {}).get("addressCity", ""),
                })

            if not page_info.get("hasNextPage", False):
                break
            cursor = page_info.get("endCursor")

    return companies
