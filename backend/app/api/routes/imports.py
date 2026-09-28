from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.dependencies import DatabaseSession
from app.core.config import get_settings
from app.models.enums import ImportRowStatus
from app.models.importing import ImportFile, ImportRow
from app.schemas.importing import (
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
    ImportRowPreview,
)
from app.services.csv_import import CSVImportError
from app.services.imports import (
    ImportWorkflowError,
    confirm_csv_import,
    preview_csv_import,
)

router = APIRouter(prefix="/imports", tags=["imports"])
ALLOWED_CSV_CONTENT_TYPES = {
    "application/csv",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "text/csv",
    "text/plain",
}


def _workflow_error(exc: ImportWorkflowError | CSVImportError) -> HTTPException:
    not_found = {"account_not_found", "import_not_found"}
    conflict = {"import_not_confirmable"}
    status_code = (
        status.HTTP_404_NOT_FOUND
        if exc.code in not_found
        else status.HTTP_409_CONFLICT
        if exc.code in conflict
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": "CSV import request could not be processed"},
    )


def _preview_response(
    session: DatabaseSession,
    import_file: ImportFile,
    *,
    row_offset: int,
    row_limit: int,
) -> ImportPreviewResponse:
    rows = list(
        session.scalars(
            select(ImportRow)
            .where(ImportRow.import_file_id == import_file.id)
            .order_by(ImportRow.row_number)
            .offset(row_offset)
            .limit(row_limit + 1)
        )
    )
    visible_rows = rows[:row_limit]
    period_start, period_end = session.execute(
        select(func.min(ImportRow.transaction_date), func.max(ImportRow.transaction_date)).where(
            ImportRow.import_file_id == import_file.id,
            ImportRow.status != ImportRowStatus.INVALID,
        )
    ).one()
    amounts = session.execute(
        select(ImportRow.amount, ImportRow.direction).where(
            ImportRow.import_file_id == import_file.id,
            ImportRow.status != ImportRowStatus.INVALID,
        )
    )
    net_amount: Decimal | None = Decimal("0.00")
    for amount, direction in amounts:
        if amount is None or direction is None:
            net_amount = None
            break
        net_amount += amount if direction.value == "credit" else -amount

    return ImportPreviewResponse(
        id=import_file.id,
        account_id=import_file.account_id,
        filename=import_file.original_filename,
        status=import_file.status,
        total_rows=import_file.total_rows,
        valid_rows=import_file.valid_rows,
        possible_duplicate_rows=import_file.duplicate_rows,
        invalid_rows=import_file.invalid_rows,
        imported_rows=import_file.imported_rows,
        period_start=period_start,
        period_end=period_end,
        net_amount=net_amount,
        created_at=import_file.created_at,
        confirmed_at=import_file.confirmed_at,
        rows=[
            ImportRowPreview(
                row_number=row.row_number,
                transaction_date=row.transaction_date,
                historical_label=row.historical_label,
                description=row.description_raw,
                amount=row.amount,
                direction=row.direction,
                status=row.status,
                error_codes=row.error_codes,
                suggested_category_id=row.suggested_category_id,
            )
            for row in visible_rows
        ],
        row_offset=row_offset,
        row_limit=row_limit,
        has_more_rows=len(rows) > row_limit,
    )


@router.post("/csv/preview", response_model=ImportPreviewResponse)
async def preview_csv(
    session: DatabaseSession,
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> ImportPreviewResponse:
    settings = get_settings()
    if file.content_type and file.content_type.casefold() not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "unsupported_csv_media_type", "message": "Unsupported CSV media type"},
        )
    content = await file.read(settings.csv_upload_max_bytes + 1)
    if len(content) > settings.csv_upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "csv_too_large", "message": "CSV file exceeds the configured limit"},
        )
    try:
        import_file = preview_csv_import(
            session,
            account_id=account_id,
            filename=file.filename,
            content=content,
        )
        session.commit()
        session.refresh(import_file)
    except (ImportWorkflowError, CSVImportError) as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    return _preview_response(session, import_file, row_offset=0, row_limit=100)


@router.get("/{import_id}", response_model=ImportPreviewResponse)
def get_import(
    import_id: UUID,
    session: DatabaseSession,
    row_offset: Annotated[int, Query(ge=0)] = 0,
    row_limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ImportPreviewResponse:
    import_file = session.get(ImportFile, import_id)
    if import_file is None or import_file.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "import_not_found", "message": "Import was not found"},
        )
    return _preview_response(session, import_file, row_offset=row_offset, row_limit=row_limit)


@router.post("/{import_id}/confirm", response_model=ImportConfirmResponse)
def confirm_import(
    import_id: UUID,
    request: ImportConfirmRequest,
    session: DatabaseSession,
) -> ImportConfirmResponse:
    try:
        import_file = confirm_csv_import(
            session,
            import_id=import_id,
            duplicate_row_numbers_to_import=request.duplicate_row_numbers_to_import,
        )
        session.commit()
        session.refresh(import_file)
    except ImportWorkflowError as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    return ImportConfirmResponse(
        id=import_file.id,
        status=import_file.status,
        imported_rows=import_file.imported_rows,
        skipped_possible_duplicates=(
            max(0, import_file.duplicate_rows - len(request.duplicate_row_numbers_to_import))
        ),
        invalid_rows=import_file.invalid_rows,
        confirmed_at=import_file.confirmed_at,
    )
