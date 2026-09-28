from datetime import UTC, datetime, time
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.models.account import Account, BalanceSnapshot
from app.models.audit import AuditEvent
from app.models.category import Category, CategoryRule
from app.models.enums import (
    AuditActorType,
    BalanceSnapshotSource,
    CategoryKind,
    ClassificationMethod,
    ImportRowStatus,
    ImportStatus,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.importing import ImportFile, ImportProfile, ImportRow
from app.models.transaction import Transaction
from app.services.category_rules import CategoryRuleCandidate, RuleField, select_category_rule
from app.services.csv_import import ParsedCSVRow, file_sha256, parse_inter_csv
from app.services.deduplication import transaction_deduplication_hash


class ImportWorkflowError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sanitize_filename(filename: str | None) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name or not safe_name.casefold().endswith(".csv"):
        raise ImportWorkflowError("invalid_csv_filename")
    return safe_name[:255]


def _rules_for_direction(
    session: Session, *, direction: str, account_id: UUID
) -> list[CategoryRuleCandidate]:
    allowed_kinds = (
        {CategoryKind.EXPENSE, CategoryKind.BOTH}
        if direction == "debit"
        else {CategoryKind.INCOME, CategoryKind.BOTH}
    )
    records = session.execute(
        select(CategoryRule, Category.kind)
        .join(Category, Category.id == CategoryRule.category_id)
        .where(CategoryRule.is_active.is_(True), Category.is_active.is_(True))
    ).all()
    return [
        CategoryRuleCandidate(
            id=rule.id,
            category_id=rule.category_id,
            pattern=rule.pattern,
            priority=rule.priority,
            match_field=RuleField(rule.match_field.value),
            account_id=rule.account_id,
            active=rule.is_active,
        )
        for rule, category_kind in records
        if category_kind in allowed_kinds and rule.account_id in {None, account_id}
    ]


def _deduplication_hash(account_id: UUID, row: ParsedCSVRow) -> str | None:
    if (
        row.transaction_date is None
        or row.description_raw is None
        or row.amount is None
        or row.direction is None
    ):
        return None
    return transaction_deduplication_hash(
        account_id=account_id,
        transaction_date=row.transaction_date,
        description=row.description_raw,
        amount=row.amount,
        direction=row.direction,
    )


def preview_csv_import(
    session: Session,
    *,
    account_id: UUID,
    filename: str | None,
    content: bytes,
    actor_identifier: str = "local-user",
) -> ImportFile:
    account = session.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.deleted_at.is_(None),
            Account.is_active.is_(True),
        )
    )
    if account is None:
        raise ImportWorkflowError("account_not_found")
    if account.currency_code != "BRL":
        raise ImportWorkflowError("csv_profile_requires_brl")

    safe_filename = sanitize_filename(filename)
    content_hash = file_sha256(content)
    existing = session.scalar(
        select(ImportFile).where(
            ImportFile.account_id == account_id,
            ImportFile.sha256 == content_hash,
            ImportFile.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    parsed = parse_inter_csv(content)
    profile = session.scalar(
        select(ImportProfile).where(
            ImportProfile.institution_name == "INTER",
            ImportProfile.is_active.is_(True),
        )
    )
    debit_rules = _rules_for_direction(session, direction="debit", account_id=account_id)
    credit_rules = _rules_for_direction(session, direction="credit", account_id=account_id)

    hashes = {
        value for row in parsed.rows if (value := _deduplication_hash(account_id, row)) is not None
    }
    existing_hashes: set[str] = set()
    hash_list = list(hashes)
    for start in range(0, len(hash_list), 500):
        existing_hashes.update(
            session.scalars(
                select(Transaction.deduplication_hash).where(
                    Transaction.account_id == account_id,
                    Transaction.deleted_at.is_(None),
                    Transaction.deduplication_hash.in_(hash_list[start : start + 500]),
                )
            )
        )

    import_file = ImportFile(
        account_id=account_id,
        profile_id=profile.id if profile else None,
        original_filename=safe_filename,
        sha256=content_hash,
        file_size=len(content),
        institution_name="INTER",
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        column_mapping=parsed.column_mapping,
        status=ImportStatus.PREVIEWED,
        total_rows=len(parsed.rows),
        actor_identifier=actor_identifier,
    )
    session.add(import_file)
    session.flush()

    valid_count = duplicate_count = invalid_count = 0
    for parsed_row in parsed.rows:
        deduplication_hash = _deduplication_hash(account_id, parsed_row)
        if parsed_row.error_codes:
            row_status = ImportRowStatus.INVALID
            invalid_count += 1
        elif deduplication_hash in existing_hashes:
            row_status = ImportRowStatus.POSSIBLE_DUPLICATE
            duplicate_count += 1
        else:
            row_status = ImportRowStatus.VALID
            valid_count += 1

        suggested_category_id = None
        if parsed_row.description_raw and parsed_row.direction:
            rules = debit_rules if parsed_row.direction == "debit" else credit_rules
            selected_rule = select_category_rule(
                description=parsed_row.description_raw,
                account_id=account_id,
                rules=rules,
            )
            suggested_category_id = selected_rule.category_id if selected_rule else None

        session.add(
            ImportRow(
                import_file_id=import_file.id,
                row_number=parsed_row.row_number,
                transaction_date=parsed_row.transaction_date,
                historical_label=parsed_row.historical_label,
                description_raw=parsed_row.description_raw,
                description_normalized=parsed_row.description_normalized,
                amount=parsed_row.amount,
                direction=(
                    TransactionDirection(parsed_row.direction) if parsed_row.direction else None
                ),
                balance_after=parsed_row.balance_after,
                deduplication_hash=deduplication_hash,
                raw_fingerprint=parsed_row.raw_fingerprint,
                status=row_status,
                error_codes=list(parsed_row.error_codes),
                suggested_category_id=suggested_category_id,
            )
        )

    import_file.valid_rows = valid_count
    import_file.duplicate_rows = duplicate_count
    import_file.invalid_rows = invalid_count
    session.add(
        AuditEvent(
            aggregate_type="import_file",
            aggregate_id=import_file.id,
            action="csv_preview_created",
            changed_fields=["status", "total_rows", "valid_rows", "duplicate_rows", "invalid_rows"],
            actor_type=AuditActorType.USER,
            actor_identifier=actor_identifier,
        )
    )
    session.flush()
    return import_file


def confirm_csv_import(
    session: Session,
    *,
    import_id: UUID,
    duplicate_row_numbers_to_import: set[int] | None = None,
    actor_identifier: str = "local-user",
) -> ImportFile:
    duplicate_row_numbers_to_import = duplicate_row_numbers_to_import or set()
    import_file = session.scalar(
        select(ImportFile).where(ImportFile.id == import_id).with_for_update()
    )
    if import_file is None or import_file.deleted_at is not None:
        raise ImportWorkflowError("import_not_found")
    if import_file.status == ImportStatus.IMPORTED:
        return import_file
    if import_file.status != ImportStatus.PREVIEWED:
        raise ImportWorkflowError("import_not_confirmable")

    rows = list(
        session.scalars(
            select(ImportRow)
            .where(ImportRow.import_file_id == import_file.id)
            .order_by(ImportRow.row_number)
        )
    )
    known_duplicate_rows = {
        row.row_number for row in rows if row.status == ImportRowStatus.POSSIBLE_DUPLICATE
    }
    if not duplicate_row_numbers_to_import <= known_duplicate_rows:
        raise ImportWorkflowError("invalid_duplicate_row_selection")

    imported_count = 0
    for row in rows:
        should_import = row.status == ImportRowStatus.VALID or (
            row.status == ImportRowStatus.POSSIBLE_DUPLICATE
            and row.row_number in duplicate_row_numbers_to_import
        )
        if not should_import:
            continue
        if (
            row.transaction_date is None
            or row.description_raw is None
            or row.description_normalized is None
            or row.amount is None
            or row.direction is None
            or row.deduplication_hash is None
        ):
            raise ImportWorkflowError("preview_row_incomplete")

        transaction = Transaction(
            account_id=import_file.account_id,
            type=(
                TransactionType.EXPENSE
                if row.direction == TransactionDirection.DEBIT
                else TransactionType.INCOME
            ),
            direction=row.direction,
            status=TransactionStatus.POSTED,
            amount=row.amount,
            transaction_date=row.transaction_date,
            description_raw=row.description_raw,
            description_normalized=row.description_normalized,
            category_id=row.suggested_category_id,
            source=TransactionSource.CSV,
            external_id=f"{import_file.sha256}:{row.row_number}",
            source_file_id=import_file.id,
            classification_method=(
                ClassificationMethod.RULE
                if row.suggested_category_id
                else ClassificationMethod.MANUAL
            ),
            is_reviewed=False,
            deduplication_hash=row.deduplication_hash,
        )
        session.add(transaction)
        session.flush()
        row.transaction_id = transaction.id
        row.status = ImportRowStatus.IMPORTED
        imported_count += 1

    snapshot_candidates = [
        row
        for row in rows
        if row.transaction_date is not None
        and row.balance_after is not None
        and row.status != ImportRowStatus.INVALID
    ]
    if snapshot_candidates:
        latest_date = max(
            row.transaction_date for row in snapshot_candidates if row.transaction_date
        )
        latest_row = min(
            (row for row in snapshot_candidates if row.transaction_date == latest_date),
            key=lambda row: row.row_number,
        )
        local_end_of_day = datetime.combine(
            latest_date, time.max, ZoneInfo(get_settings().timezone)
        )
        session.add(
            BalanceSnapshot(
                account_id=import_file.account_id,
                amount=latest_row.balance_after,
                currency_code="BRL",
                source=BalanceSnapshotSource.CSV,
                observed_at=local_end_of_day.astimezone(UTC),
                external_id=import_file.sha256,
            )
        )

    import_file.imported_rows = imported_count
    import_file.status = ImportStatus.IMPORTED
    import_file.confirmed_at = utc_now()
    session.add(
        AuditEvent(
            aggregate_type="import_file",
            aggregate_id=import_file.id,
            action="csv_import_confirmed",
            changed_fields=["status", "imported_rows", "confirmed_at"],
            actor_type=AuditActorType.USER,
            actor_identifier=actor_identifier,
        )
    )
    session.flush()
    return import_file
