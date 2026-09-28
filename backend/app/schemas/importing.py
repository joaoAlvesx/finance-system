from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ImportRowStatus, ImportStatus, TransactionDirection


class ImportRowPreview(BaseModel):
    row_number: int
    transaction_date: date | None
    historical_label: str | None
    description: str | None
    amount: Decimal | None
    direction: TransactionDirection | None
    status: ImportRowStatus
    error_codes: list[str]
    suggested_category_id: UUID | None


class ImportPreviewResponse(BaseModel):
    id: UUID
    account_id: UUID
    filename: str
    status: ImportStatus
    total_rows: int
    valid_rows: int
    possible_duplicate_rows: int
    invalid_rows: int
    imported_rows: int
    period_start: date | None
    period_end: date | None
    net_amount: Decimal | None
    created_at: datetime
    confirmed_at: datetime | None
    rows: list[ImportRowPreview]
    row_offset: int
    row_limit: int
    has_more_rows: bool


class ImportConfirmRequest(BaseModel):
    duplicate_row_numbers_to_import: set[int] = Field(default_factory=set)


class ImportConfirmResponse(BaseModel):
    id: UUID
    status: ImportStatus
    imported_rows: int
    skipped_possible_duplicates: int
    invalid_rows: int
    confirmed_at: datetime
