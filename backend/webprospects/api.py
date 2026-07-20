import logging

import httpx
from django.shortcuts import get_object_or_404
from ninja import Router

from .models import WebProspectRecord, WebProspectRun
from .schemas import (
    CreateOneRequest,
    CreateOneResponse,
    RunDetailOut,
    RunOut,
    RunRequest,
    ScrapedRecord,
    ScrapeRequest,
    ScrapeResponse,
    UpdateExistingRequest,
    UpdateExistingResponse,
)
from .scrapers import SCRAPERS, suggest_scraper
from .services import (
    MSP_COMPANY_TYPE_VALUE,
    apply_update,
    compute_missing,
    fetch_company,
    fetch_company_people,
    find_companies_by_name,
    process_record,
)

logger = logging.getLogger(__name__)
router = Router()

USER_AGENT = "Mozilla/5.0 (compatible; prospect-webscraper/1.0)"


def _fetch_html(url: str) -> str:
    response = httpx.get(
        url, timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.text


def _missing_fields(record: dict) -> list[str]:
    from .services import _missing_fields as mf
    return mf(record)


@router.get("/suggest-scraper")
def suggest(request, url: str):
    return {"scraper": suggest_scraper(url)}


@router.post("/scrape", response={200: ScrapeResponse, 400: dict, 502: dict})
def scrape(request, payload: ScrapeRequest):
    scraper_key = payload.scraper or suggest_scraper(payload.url)
    if scraper_key not in SCRAPERS:
        return 400, {"detail": f"No scraper available for this URL (got '{scraper_key}')."}

    try:
        html = _fetch_html(payload.url)
    except httpx.HTTPError as e:
        return 502, {"detail": f"Failed to fetch page: {e}"}

    parsed = SCRAPERS[scraper_key](html)

    records: list[ScrapedRecord] = []
    ambiguous = False
    for rec in parsed:
        existing = []
        try:
            existing = find_companies_by_name(rec["name"]) if rec.get("name") else []
        except httpx.HTTPError as e:
            logger.warning("Existence check failed for %s: %s", rec.get("name"), e)
        if len(existing) > 1:
            ambiguous = True

        # For an existing record, automatically compute which essential fields
        # are absent in Twenty so the card can offer Update-or-Skip directly.
        missing_essential = []
        if existing:
            try:
                people = fetch_company_people(existing[0]["id"])
                missing_essential = [
                    {k: v for k, v in m.items() if not k.startswith("_")}
                    for m in compute_missing(existing[0], people, rec)
                ]
            except httpx.HTTPError as e:
                logger.warning("Diff check failed for %s: %s", rec.get("name"), e)

        records.append(ScrapedRecord(
            record=rec,
            missing_fields=_missing_fields(rec),
            existing_count=len(existing),
            existing_ids=[c.get("id", "") for c in existing],
            missing_essential=missing_essential,
        ))

    return 200, ScrapeResponse(
        scraper=scraper_key,
        source_url=payload.url,
        records=records,
        total=len(records),
        ambiguous=ambiguous,
    )


def _get_or_create_run(run_id: int | None, source_url: str, scraper: str,
                       ask_confirmation: bool) -> WebProspectRun:
    if run_id is not None:
        return get_object_or_404(WebProspectRun, id=run_id)
    return WebProspectRun.objects.create(
        source_url=source_url,
        scraper=scraper or "apmsl",
        ask_confirmation=ask_confirmation,
    )


@router.post("/create-one", response=CreateOneResponse)
def create_one(request, payload: CreateOneRequest):
    """Create a single (confirmed/edited) MSP and record it against a run."""
    run = _get_or_create_run(
        payload.run_id, payload.source_url,
        suggest_scraper(payload.source_url) or "apmsl",
        ask_confirmation=True,
    )
    record = payload.record.dict()

    status = None
    twenty_id = ""
    error = ""
    dup_id = ""
    dup_name = ""
    missing = _missing_fields(record)

    existing = []
    if payload.skip_if_exists and record.get("name"):
        try:
            existing = find_companies_by_name(record["name"])
        except httpx.HTTPError as e:
            error = f"Existence check failed: {e}"

    if existing:
        status = "already_present"
        twenty_id = existing[0].get("id", "")
    elif error:
        status = "failed"
    else:
        company_type = MSP_COMPANY_TYPE_VALUE if payload.set_company_type else None
        result = process_record(record, company_type)
        status = result["status"]
        twenty_id = result["twenty_company_id"]
        missing = result["missing_fields"]
        error = result["error"]
        owner = result.get("duplicate_owner")
        if owner:
            dup_id, dup_name = owner["company_id"], owner["company_name"]

    WebProspectRecord.objects.create(
        run=run, name=record.get("name", ""), status=status,
        twenty_company_id=twenty_id, missing_fields=missing, error=error,
        duplicate_company_id=dup_id, duplicate_company_name=dup_name, data=record,
    )
    _recount(run)

    return CreateOneResponse(
        run_id=run.id, status=status, twenty_company_id=twenty_id,
        missing_fields=missing, error=error,
        duplicate_company_id=dup_id, duplicate_company_name=dup_name,
    )


@router.post("/update-existing", response=UpdateExistingResponse)
def update_existing(request, payload: UpdateExistingRequest):
    """Fill missing essential data on an existing Twenty MSP (no duplicate)."""
    run = _get_or_create_run(
        payload.run_id, payload.source_url,
        suggest_scraper(payload.source_url) or "apmsl",
        ask_confirmation=True,
    )
    record = payload.record.dict()

    status = "updated"
    error = ""
    dup_id = ""
    dup_name = ""
    updated_fields: list[str] = []
    try:
        company = fetch_company(payload.company_id)
        people = fetch_company_people(payload.company_id)
        diff = compute_missing(company, people, record)
        result = apply_update(company, diff, record)
        updated_fields = result["updated_fields"]
        if result.get("skipped"):
            error = (
                f"{'/'.join(result['skipped'])} already exists elsewhere in Twenty (skipped)"
            )
            owner = result.get("duplicate_owner")
            if owner:
                dup_id, dup_name = owner["company_id"], owner["company_name"]
    except httpx.HTTPStatusError as e:
        status = "failed"
        error = e.response.text[:500]
    except Exception as e:  # noqa: BLE001
        status = "failed"
        error = str(e)[:500]

    WebProspectRecord.objects.create(
        run=run, name=record.get("name", ""), status=status,
        twenty_company_id=payload.company_id, missing_fields=updated_fields,
        error=error, duplicate_company_id=dup_id, duplicate_company_name=dup_name,
        data=record,
    )
    _recount(run)

    return UpdateExistingResponse(
        run_id=run.id, status=status, twenty_company_id=payload.company_id,
        updated_fields=updated_fields, error=error,
        duplicate_company_id=dup_id, duplicate_company_name=dup_name,
    )


@router.post("/run", response={202: dict, 400: dict})
def run_all(request, payload: RunRequest):
    """Scrape and create all records without per-card confirmation (async)."""
    scraper_key = payload.scraper or suggest_scraper(payload.url)
    if scraper_key not in SCRAPERS:
        return 400, {"detail": f"No scraper available for this URL (got '{scraper_key}')."}

    from .tasks import run_web_prospects

    task = run_web_prospects.delay(
        url=payload.url,
        scraper_key=scraper_key,
        set_company_type=payload.set_company_type,
        skip_if_exists=payload.skip_if_exists,
    )
    return 202, {"task_id": task.id}


@router.get("/run-status")
def run_status(request, task_id: str):
    from .tasks import run_web_prospects

    result = run_web_prospects.AsyncResult(task_id)
    if result.state == "PROGRESS":
        info = result.info or {}
        return {"state": "PROGRESS", **info}
    if result.state == "SUCCESS":
        return {"state": "SUCCESS", **(result.result or {})}
    if result.state == "FAILURE":
        return {"state": "FAILED", "error": str(result.result)}
    return {"state": result.state}


@router.post("/cancel-run")
def cancel_run(request, task_id: str):
    """Ask a running automatic run to stop gracefully after the current record."""
    from .tasks import request_cancel, run_web_prospects

    request_cancel(task_id)
    # Best-effort hard revoke as a fallback if the task is stuck between checks.
    run_web_prospects.AsyncResult(task_id).revoke()
    return {"cancelled": True, "task_id": task_id}


@router.get("/runs", response=list[RunOut])
def list_runs(request):
    return WebProspectRun.objects.all()


@router.get("/runs/{run_id}", response=RunDetailOut)
def run_detail(request, run_id: int):
    run = get_object_or_404(WebProspectRun, id=run_id)
    data = RunDetailOut.from_orm(run)
    data.records = [
        {
            "id": r.id, "name": r.name, "status": r.status,
            "twenty_company_id": r.twenty_company_id,
            "missing_fields": r.missing_fields, "error": r.error,
            "duplicate_company_id": r.duplicate_company_id,
            "duplicate_company_name": r.duplicate_company_name,
        }
        for r in run.records.all()
    ]
    return data


def _recount(run: WebProspectRun):
    qs = run.records.all()
    run.total = qs.count()
    run.created_count = qs.filter(status="created").count()
    run.updated_count = qs.filter(status="updated").count()
    run.skipped_count = qs.filter(status="skipped").count()
    run.already_present_count = qs.filter(status="already_present").count()
    run.failed_count = qs.filter(status="failed").count()
    run.save()
