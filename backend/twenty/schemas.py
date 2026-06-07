from datetime import datetime

from ninja import Schema


class TransformerOut(Schema):
    id: int
    name: str
    company_type_id: int
    csv_name_column: str
    csv_email_column: str
    csv_postcode_column: str
    csv_domain_column: str
    csv_delimiter: str


class TransformerIn(Schema):
    name: str
    company_type_id: int
    csv_name_column: str
    csv_email_column: str
    csv_postcode_column: str
    csv_domain_column: str = ""
    csv_delimiter: str = ";"


class CsvUploadResponse(Schema):
    headers: list[str]
    row_count: int
    upload_id: str


class PreviewRow(Schema):
    name: str
    email: str
    postcode: str
    domain: str


class PreviewResponse(Schema):
    rows: list[PreviewRow]
    total_deduplicated: int


class ImportRequest(Schema):
    upload_id: str
    transformer_id: int
    company_type_id: int


class ImportResultRow(Schema):
    name: str
    status: str  # "created", "skipped", "failed"
    error: str = ""


class ImportResponse(Schema):
    created: int
    skipped: int
    failed: int
    details: list[ImportResultRow]


class ImportStartResponse(Schema):
    task_id: str


class ImportStatusResponse(Schema):
    state: str
    processed: int
    total: int
    created: int
    skipped: int
    failed: int
    details: list[ImportResultRow] = []
    error: str = ""
