from datetime import datetime

from ninja import Schema


class PersonData(Schema):
    first_name: str = ""
    last_name: str = ""


class MspRecord(Schema):
    """A scraped (and possibly user-edited) MSP record."""
    name: str = ""
    address_line1: str = ""
    postcode: str = ""
    city: str = ""
    finess_number: str = ""
    finess_date: str = ""
    project_type: str = ""
    coordinators: list[PersonData] = []
    team_leaders: list[PersonData] = []
    email: str = ""
    phone: str = ""
    website: str = ""


class ScrapeRequest(Schema):
    url: str
    scraper: str | None = None


class DiffEntry(Schema):
    field: str        # email | phone | domain | address
    label: str
    value: str
    target: str       # company | contact_person


class ScrapedRecord(Schema):
    """A scraped record plus its Twenty existence check."""
    record: MspRecord
    missing_fields: list[str] = []
    existing_count: int = 0
    existing_ids: list[str] = []
    # For existing records: which essential fields are absent in Twenty and
    # would be filled by an update. Empty when the record is new or complete.
    missing_essential: list[DiffEntry] = []


class ScrapeResponse(Schema):
    scraper: str
    source_url: str
    records: list[ScrapedRecord]
    total: int
    # True when at least one record matches more than one Twenty company —
    # the frontend should propose to cancel.
    ambiguous: bool = False


class CreateOneRequest(Schema):
    run_id: int | None = None
    source_url: str
    record: MspRecord
    set_company_type: bool = True
    # When True, skip creation if the company already exists in Twenty.
    skip_if_exists: bool = True


class CreateOneResponse(Schema):
    run_id: int
    status: str  # created | already_present | skipped | failed
    twenty_company_id: str = ""
    missing_fields: list[str] = []
    error: str = ""
    duplicate_company_id: str = ""
    duplicate_company_name: str = ""


class UpdateExistingRequest(Schema):
    run_id: int | None = None
    source_url: str
    company_id: str
    record: MspRecord


class UpdateExistingResponse(Schema):
    run_id: int
    status: str  # updated | failed
    twenty_company_id: str = ""
    updated_fields: list[str] = []
    error: str = ""
    duplicate_company_id: str = ""
    duplicate_company_name: str = ""


class RunRequest(Schema):
    """Scrape a URL and create every record without per-card confirmation."""
    url: str
    scraper: str | None = None
    set_company_type: bool = True
    skip_if_exists: bool = True


class RecordOut(Schema):
    id: int
    name: str
    status: str
    twenty_company_id: str
    missing_fields: list[str]
    error: str
    duplicate_company_id: str = ""
    duplicate_company_name: str = ""


class RunOut(Schema):
    id: int
    source_url: str
    scraper: str
    ask_confirmation: bool
    total: int
    created_count: int
    updated_count: int
    skipped_count: int
    already_present_count: int
    failed_count: int
    created_at: datetime


class RunDetailOut(RunOut):
    records: list[RecordOut]
