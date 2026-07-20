import logging

import httpx
from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _cancel_key(task_id: str) -> str:
    return f"webprospects:cancel:{task_id}"


def request_cancel(task_id: str):
    """Flag a running task to stop gracefully after the current record."""
    cache.set(_cancel_key(task_id), True, timeout=3600)


def _is_cancelled(task_id: str) -> bool:
    return bool(cache.get(_cancel_key(task_id)))


@shared_task(bind=True)
def run_web_prospects(self, url, scraper_key, set_company_type=True, skip_if_exists=True):
    from .models import WebProspectRecord, WebProspectRun
    from .scrapers import SCRAPERS
    from .services import (
        MSP_COMPANY_TYPE_VALUE,
        find_companies_by_name,
        process_record,
    )

    headers = {"User-Agent": "Mozilla/5.0 (compatible; prospect-webscraper/1.0)"}
    try:
        resp = httpx.get(url, timeout=60, follow_redirects=True, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return {"status": "error", "error": f"Failed to fetch page: {e}"}

    records = SCRAPERS[scraper_key](resp.text)
    total = len(records)

    run = WebProspectRun.objects.create(
        source_url=url, scraper=scraper_key, ask_confirmation=False, total=total,
    )

    company_type = MSP_COMPANY_TYPE_VALUE if set_company_type else None
    counts = {"created": 0, "updated": 0, "already_present": 0, "skipped": 0, "failed": 0}
    cancelled = False

    for i, record in enumerate(records, start=1):
        if _is_cancelled(self.request.id):
            cancelled = True
            break
        status = "failed"
        twenty_id = ""
        error = ""
        missing = []
        dup_id = ""
        dup_name = ""
        try:
            from .services import (
                apply_update,
                compute_missing,
                fetch_company_people,
                find_probable_duplicates,
            )

            existing = (
                find_companies_by_name(record["name"])
                if skip_if_exists and record.get("name") else []
            )
            if existing:
                # Already in Twenty: enrich it with any missing essential data.
                company = existing[0]
                twenty_id = company.get("id", "")
                people = fetch_company_people(twenty_id)
                diff = compute_missing(company, people, record)
                if diff:
                    result = apply_update(company, diff, record)
                    status = "updated"
                    missing = result["updated_fields"]
                    if result.get("skipped"):
                        error = f"{'/'.join(result['skipped'])} already exists elsewhere (skipped)"
                        owner = result.get("duplicate_owner")
                        if owner:
                            dup_id, dup_name = owner["company_id"], owner["company_name"]
                else:
                    status = "already_present"
            else:
                # Not found by name — ask Twenty for a probable duplicate
                # (matches exact name / domain) before creating.
                probable = (
                    find_probable_duplicates(record)
                    if skip_if_exists and record.get("name") else []
                )
                if probable:
                    status = "already_present"
                    twenty_id = probable[0]["id"]
                    dup_id = probable[0]["id"]
                    dup_name = probable[0]["name"]
                    error = f"Probable duplicate of “{probable[0]['name']}” (skipped creation)"
                else:
                    result = process_record(record, company_type)
                    status = result["status"]
                    twenty_id = result["twenty_company_id"]
                    missing = result["missing_fields"]
                    error = result["error"]
                    owner = result.get("duplicate_owner")
                    if owner:
                        dup_id, dup_name = owner["company_id"], owner["company_name"]
        except httpx.HTTPError as e:
            error = str(e)[:500]

        counts[status] = counts.get(status, 0) + 1
        WebProspectRecord.objects.create(
            run=run, name=record.get("name", ""), status=status,
            duplicate_company_id=dup_id, duplicate_company_name=dup_name,
            twenty_company_id=twenty_id, missing_fields=missing, error=error, data=record,
        )

        self.update_state(state="PROGRESS", meta={
            "processed": i, "total": total, "run_id": run.id, **counts,
        })

    run.created_count = counts["created"]
    run.updated_count = counts["updated"]
    run.already_present_count = counts["already_present"]
    run.skipped_count = counts["skipped"]
    run.failed_count = counts["failed"]
    run.save()

    cache.delete(_cancel_key(self.request.id))

    return {"run_id": run.id, "total": total, "cancelled": cancelled, **counts}
