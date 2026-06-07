import logging

import httpx
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def import_companies(self, upload_id, transformer_id, company_type_id):
    from emails.models import CompanyType

    from .models import ImportRun, Transformer
    from .services import (
        create_company_in_twenty,
        delete_csv,
        find_company_by_name,
        parse_and_deduplicate,
        retrieve_csv,
    )

    content = retrieve_csv(upload_id)
    if content is None:
        return {
            "status": "error",
            "error": "Upload expired or not found. Please re-upload the CSV.",
        }

    transformer = Transformer.objects.get(id=transformer_id)
    company_type = CompanyType.objects.get(id=company_type_id)

    companies = parse_and_deduplicate(content, transformer)
    total = len(companies)
    results = {"created": 0, "skipped": 0, "failed": 0, "details": []}

    for i, company in enumerate(companies, start=1):
        try:
            existing = find_company_by_name(company["name"])
            if existing:
                results["skipped"] += 1
                results["details"].append({
                    "name": company["name"],
                    "status": "skipped",
                    "error": "Already exists in Twenty CRM",
                })
            else:
                create_company_in_twenty(company, company_type.name)
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

        self.update_state(
            state="PROGRESS",
            meta={
                "processed": i,
                "total": total,
                "created": results["created"],
                "skipped": results["skipped"],
                "failed": results["failed"],
            },
        )

    ImportRun.objects.create(
        transformer=transformer,
        company_type=company_type,
        total_rows=total,
        deduplicated_count=total,
        created_count=results["created"],
        skipped_count=results["skipped"],
        failed_count=results["failed"],
        errors=[d for d in results["details"] if d.get("error")],
    )

    delete_csv(upload_id)

    return results
