import logging

import httpx
from celery import shared_task

logger = logging.getLogger(__name__)


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
    counts = {"created": 0, "already_present": 0, "skipped": 0, "failed": 0}

    for i, record in enumerate(records, start=1):
        status = "failed"
        twenty_id = ""
        error = ""
        missing = []
        try:
            existing = (
                find_companies_by_name(record["name"])
                if skip_if_exists and record.get("name") else []
            )
            if existing:
                status = "already_present"
                twenty_id = existing[0].get("id", "")
                from .services import _missing_fields
                missing = _missing_fields(record)
            else:
                result = process_record(record, company_type)
                status = result["status"]
                twenty_id = result["twenty_company_id"]
                missing = result["missing_fields"]
                error = result["error"]
        except httpx.HTTPError as e:
            error = str(e)[:500]

        counts[status] = counts.get(status, 0) + 1
        WebProspectRecord.objects.create(
            run=run, name=record.get("name", ""), status=status,
            twenty_company_id=twenty_id, missing_fields=missing, error=error, data=record,
        )

        self.update_state(state="PROGRESS", meta={
            "processed": i, "total": total, "run_id": run.id, **counts,
        })

    run.created_count = counts["created"]
    run.already_present_count = counts["already_present"]
    run.skipped_count = counts["skipped"]
    run.failed_count = counts["failed"]
    run.save()

    return {"run_id": run.id, "total": total, **counts}
