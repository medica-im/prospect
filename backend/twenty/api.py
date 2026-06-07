import logging

from django.shortcuts import get_object_or_404
from ninja import File, Router, UploadedFile

from emails.models import CompanyType

from .models import Transformer
from .schemas import (
    CsvUploadResponse,
    ImportRequest,
    ImportStartResponse,
    ImportStatusResponse,
    PreviewResponse,
    PreviewRow,
    TransformerIn,
    TransformerOut,
)
from .services import (
    parse_csv_headers,
    preview_rows,
    retrieve_csv,
    store_csv,
)

logger = logging.getLogger(__name__)
router = Router()


@router.get("/transformers", response=list[TransformerOut])
def list_transformers(request, company_type_id: int | None = None):
    qs = Transformer.objects.all()
    if company_type_id is not None:
        qs = qs.filter(company_type_id=company_type_id)
    return qs


@router.post("/transformers", response={201: TransformerOut})
def create_transformer(request, payload: TransformerIn):
    transformer = Transformer.objects.create(**payload.dict())
    return 201, transformer


@router.post("/upload-csv", response=CsvUploadResponse)
def upload_csv(request, file: UploadedFile = File(...), delimiter: str = ";"):
    content = file.read()
    upload_id = store_csv(content)
    headers, row_count = parse_csv_headers(content, delimiter)
    return CsvUploadResponse(
        headers=headers,
        row_count=row_count,
        upload_id=upload_id,
    )


@router.post("/preview", response=PreviewResponse)
def preview_import(request, upload_id: str, transformer_id: int):
    content = retrieve_csv(upload_id)
    if content is None:
        return 404, {"detail": "Upload expired or not found"}

    transformer = get_object_or_404(Transformer, id=transformer_id)
    sample, total = preview_rows(content, transformer)

    return PreviewResponse(
        rows=[PreviewRow(**row) for row in sample],
        total_deduplicated=total,
    )


@router.post("/import", response={202: ImportStartResponse})
def execute_import(request, payload: ImportRequest):
    content = retrieve_csv(payload.upload_id)
    if content is None:
        return 404, {"detail": "Upload expired or not found"}

    get_object_or_404(Transformer, id=payload.transformer_id)
    get_object_or_404(CompanyType, id=payload.company_type_id)

    from .tasks import import_companies

    task = import_companies.delay(
        upload_id=payload.upload_id,
        transformer_id=payload.transformer_id,
        company_type_id=payload.company_type_id,
    )

    return 202, ImportStartResponse(task_id=task.id)


@router.get("/import-status", response=ImportStatusResponse)
def import_status(request, task_id: str):
    from .tasks import import_companies

    result = import_companies.AsyncResult(task_id)

    if result.state == "PENDING":
        return ImportStatusResponse(
            state="PENDING", processed=0, total=0,
            created=0, skipped=0, failed=0,
        )
    elif result.state == "PROGRESS":
        info = result.info
        return ImportStatusResponse(
            state="PROGRESS",
            processed=info.get("processed", 0),
            total=info.get("total", 0),
            created=info.get("created", 0),
            skipped=info.get("skipped", 0),
            failed=info.get("failed", 0),
        )
    elif result.state == "SUCCESS":
        info = result.result
        if info.get("status") == "error":
            return ImportStatusResponse(
                state="FAILED", processed=0, total=0,
                created=0, skipped=0, failed=0,
                error=info.get("error", "Unknown error"),
            )
        return ImportStatusResponse(
            state="SUCCESS",
            processed=info.get("created", 0) + info.get("skipped", 0) + info.get("failed", 0),
            total=info.get("created", 0) + info.get("skipped", 0) + info.get("failed", 0),
            created=info.get("created", 0),
            skipped=info.get("skipped", 0),
            failed=info.get("failed", 0),
            details=info.get("details", []),
        )
    elif result.state == "FAILURE":
        return ImportStatusResponse(
            state="FAILED", processed=0, total=0,
            created=0, skipped=0, failed=0,
            error=str(result.result),
        )
    else:
        return ImportStatusResponse(
            state=result.state, processed=0, total=0,
            created=0, skipped=0, failed=0,
        )
