import csv
import io
import random
import uuid

import httpx
from django.conf import settings
from django.core.cache import cache

from .models import Transformer


# --- CSV temporary storage (Redis cache, 30-min TTL) ---

def store_csv(content: bytes) -> str:
    upload_id = str(uuid.uuid4())
    cache.set(f"csv_upload:{upload_id}", content, timeout=1800)
    return upload_id


def retrieve_csv(upload_id: str) -> bytes | None:
    return cache.get(f"csv_upload:{upload_id}")


def delete_csv(upload_id: str):
    cache.delete(f"csv_upload:{upload_id}")


# --- CSV Parsing ---

def parse_csv_headers(content: bytes, delimiter: str = ";") -> tuple[list[str], int]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames or []
    rows = list(reader)
    return list(headers), len(rows)


def parse_and_deduplicate(content: bytes, transformer: Transformer) -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=transformer.csv_delimiter)

    seen_names: dict[str, dict] = {}
    for row in reader:
        name = row.get(transformer.csv_name_column, "").strip()
        if not name:
            continue
        if name in seen_names:
            continue

        email = row.get(transformer.csv_email_column, "").strip()
        raw_postcode = row.get(transformer.csv_postcode_column, "").strip()
        postcode = raw_postcode[:2].zfill(2)
        domain = ""
        if transformer.csv_domain_column:
            domain = row.get(transformer.csv_domain_column, "").strip()

        seen_names[name] = {
            "name": name,
            "email": email,
            "postcode": postcode,
            "domain": domain,
        }

    return list(seen_names.values())


def preview_rows(content: bytes, transformer: Transformer, count: int = 3) -> tuple[list[dict], int]:
    all_rows = parse_and_deduplicate(content, transformer)
    sample = random.sample(all_rows, min(count, len(all_rows)))
    return sample, len(all_rows)


# --- Twenty CRM API ---

def find_company_by_name(name: str) -> dict | None:
    headers = {
        "Authorization": f"Bearer {settings.TWENTY_API_KEY}",
    }
    response = httpx.get(
        f"{settings.TWENTY_API_URL}/rest/companies",
        headers=headers,
        params={"filter": f'name[ilike]:"{name}"'},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json().get("data", {}).get("companies", [])
    return data[0] if data else None


def create_company_in_twenty(company: dict, company_type_name: str) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.TWENTY_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "name": company["name"],
        "email": {"primaryEmail": company["email"]},
        "domainName": {"primaryLinkUrl": company["domain"]},
        "address": {"addressPostcode": company["postcode"]},
        "companyType": company_type_name,
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{settings.TWENTY_API_URL}/rest/companies",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        return response.json()


def run_import(content: bytes, transformer: Transformer, company_type_name: str) -> dict:
    companies = parse_and_deduplicate(content, transformer)
    results = {"created": 0, "skipped": 0, "failed": 0, "details": []}

    for company in companies:
        try:
            existing = find_company_by_name(company["name"])
            if existing:
                results["skipped"] += 1
                results["details"].append({
                    "name": company["name"],
                    "status": "skipped",
                    "error": "Already exists in Twenty CRM",
                })
                continue
            create_company_in_twenty(company, company_type_name)
            results["created"] += 1
            results["details"].append({
                "name": company["name"],
                "status": "created",
            })
        except httpx.HTTPStatusError as e:
            results["failed"] += 1
            results["details"].append({
                "name": company["name"],
                "status": "failed",
                "error": e.response.text[:500],
            })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "name": company["name"],
                "status": "failed",
                "error": str(e)[:500],
            })

    return results
