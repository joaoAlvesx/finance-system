import base64
import json
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select

from app.api.dependencies import DatabaseSession
from app.db.base import utc_now
from app.models.account import Account, TransferGroup
from app.models.audit import AuditEvent
from app.models.category import Category, CategoryRule
from app.models.enums import (
    AuditActorType,
    ClassificationMethod,
    RuleMatchField,
    RuleOrigin,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.transaction import Transaction
from app.schemas.transactions import (
    SimilarTransactionsCategoryResult,
    SimilarTransactionsCategoryUpdate,
    TransactionCreate,
    TransactionPage,
    TransactionPatch,
    TransactionRead,
    TransferCreate,
    TransferRead,
)
from app.services.deduplication import (
    descriptions_share_recipient,
    normalize_description,
    recipient_rule_pattern,
    transaction_deduplication_hash,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": code, "message": message},
    )


def _encode_cursor(transaction: Transaction) -> str:
    payload = json.dumps(
        {"date": transaction.transaction_date.isoformat(), "id": str(transaction.id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return date.fromisoformat(payload["date"]), UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_cursor", "message": "Transaction cursor is invalid"},
        ) from exc


def _active_account(session: DatabaseSession, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.deleted_at is not None or not account.is_active:
        raise _not_found("account_not_found", "Account was not found")
    return account


def _active_category(session: DatabaseSession, category_id: UUID | None) -> Category | None:
    if category_id is None:
        return None
    category = session.get(Category, category_id)
    if category is None or not category.is_active:
        raise _not_found("category_not_found", "Category was not found")
    return category


@router.get("", response_model=TransactionPage)
def list_transactions(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    source: TransactionSource | None = None,
    transaction_status: TransactionStatus | None = None,
    is_reviewed: bool | None = None,
    uncategorized: bool | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> TransactionPage:
    statement = select(Transaction).where(Transaction.deleted_at.is_(None))
    if account_id:
        statement = statement.where(Transaction.account_id == account_id)
    if category_id:
        statement = statement.where(Transaction.category_id == category_id)
    if source:
        statement = statement.where(Transaction.source == source)
    if transaction_status:
        statement = statement.where(Transaction.status == transaction_status)
    if is_reviewed is not None:
        statement = statement.where(Transaction.is_reviewed.is_(is_reviewed))
    if uncategorized is not None:
        statement = statement.where(
            Transaction.category_id.is_(None)
            if uncategorized
            else Transaction.category_id.is_not(None)
        )
    if search:
        statement = statement.where(Transaction.description_raw.ilike(f"%{search.strip()}%"))
    if date_from:
        statement = statement.where(Transaction.transaction_date >= date_from)
    if date_to:
        statement = statement.where(Transaction.transaction_date <= date_to)
    if cursor:
        cursor_date, cursor_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Transaction.transaction_date < cursor_date,
                and_(
                    Transaction.transaction_date == cursor_date,
                    Transaction.id < cursor_id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(
                limit + 1
            )
        )
    )
    items = rows[:limit]
    return TransactionPage(
        items=[TransactionRead.model_validate(item) for item in items],
        next_cursor=_encode_cursor(items[-1]) if len(rows) > limit else None,
    )


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(request: TransactionCreate, session: DatabaseSession) -> Transaction:
    _active_account(session, request.account_id)
    _active_category(session, request.category_id)
    normalized = normalize_description(request.description)
    transaction = Transaction(
        account_id=request.account_id,
        type=request.type,
        direction=request.direction,
        status=request.status,
        amount=request.amount,
        transaction_date=request.transaction_date,
        description_raw=request.description.strip(),
        description_normalized=normalized,
        category_id=request.category_id,
        source=TransactionSource.MANUAL,
        classification_method=ClassificationMethod.MANUAL,
        is_reviewed=True,
        notes=request.notes,
        deduplication_hash=transaction_deduplication_hash(
            account_id=request.account_id,
            transaction_date=request.transaction_date,
            description=request.description,
            amount=request.amount,
            direction=request.direction.value,
        ),
    )
    session.add(transaction)
    session.flush()
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="transaction_created",
            changed_fields=[
                "account_id",
                "type",
                "direction",
                "status",
                "amount",
                "transaction_date",
                "description_raw",
                "category_id",
            ],
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(transaction)
    return transaction


@router.post("/transfers", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def create_transfer(request: TransferCreate, session: DatabaseSession) -> TransferRead:
    from_account = _active_account(session, request.from_account_id)
    to_account = _active_account(session, request.to_account_id)
    if from_account.currency_code != to_account.currency_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "transfer_currency_mismatch",
                "message": "Accounts use different currencies",
            },
        )
    transfer_category = session.scalar(
        select(Category).where(Category.name == "Transferências", Category.is_active.is_(True))
    )
    group = TransferGroup(notes=request.notes)
    session.add(group)
    session.flush()
    normalized = normalize_description(request.description)

    def leg(account_id: UUID, direction: TransactionDirection) -> Transaction:
        return Transaction(
            account_id=account_id,
            type=TransactionType.TRANSFER,
            direction=direction,
            status=TransactionStatus.POSTED,
            amount=request.amount,
            transaction_date=request.transaction_date,
            description_raw=request.description.strip(),
            description_normalized=normalized,
            category_id=transfer_category.id if transfer_category else None,
            source=TransactionSource.MANUAL,
            classification_method=ClassificationMethod.MANUAL,
            is_reviewed=True,
            notes=request.notes,
            deduplication_hash=transaction_deduplication_hash(
                account_id=account_id,
                transaction_date=request.transaction_date,
                description=request.description,
                amount=request.amount,
                direction=direction.value,
            ),
            transfer_group_id=group.id,
        )

    debit = leg(request.from_account_id, TransactionDirection.DEBIT)
    credit = leg(request.to_account_id, TransactionDirection.CREDIT)
    session.add_all([debit, credit])
    session.flush()
    session.add(
        AuditEvent(
            aggregate_type="transfer_group",
            aggregate_id=group.id,
            action="transfer_created",
            changed_fields=["from_account_id", "to_account_id", "amount", "transaction_date"],
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(debit)
    session.refresh(credit)
    return TransferRead(
        transfer_group_id=group.id,
        debit=TransactionRead.model_validate(debit),
        credit=TransactionRead.model_validate(credit),
    )


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: UUID,
    request: TransactionPatch,
    session: DatabaseSession,
) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.deleted_at is not None:
        raise _not_found("transaction_not_found", "Transaction was not found")
    fields = request.model_fields_set
    change_data: dict[str, object] = {}
    if "category_id" in fields:
        _active_category(session, request.category_id)
        change_data["category_id"] = {
            "before": str(transaction.category_id) if transaction.category_id else None,
            "after": str(request.category_id) if request.category_id else None,
        }
        transaction.category_id = request.category_id
        transaction.classification_method = ClassificationMethod.MANUAL
    if "status" in fields and request.status is not None:
        change_data["status"] = {
            "before": transaction.status.value,
            "after": request.status.value,
        }
        transaction.status = request.status
    if "is_reviewed" in fields and request.is_reviewed is not None:
        change_data["is_reviewed"] = {
            "before": transaction.is_reviewed,
            "after": request.is_reviewed,
        }
        transaction.is_reviewed = request.is_reviewed
    if "notes" in fields:
        transaction.notes = request.notes
    if not fields:
        return transaction
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="transaction_updated",
            changed_fields=sorted(fields),
            change_data=change_data,
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(transaction)
    return transaction


@router.post(
    "/{transaction_id}/category/apply-to-similar",
    response_model=SimilarTransactionsCategoryResult,
)
def apply_category_to_similar_transactions(
    transaction_id: UUID,
    request: SimilarTransactionsCategoryUpdate,
    session: DatabaseSession,
) -> SimilarTransactionsCategoryResult:
    source = session.scalar(
        select(Transaction).where(Transaction.id == transaction_id).with_for_update()
    )
    if source is None or source.deleted_at is not None:
        raise _not_found("transaction_not_found", "Transaction was not found")
    category = _active_category(session, request.category_id)
    if category is None:
        raise _not_found("category_not_found", "Category was not found")

    candidates = session.execute(
        select(Transaction.id, Transaction.description_normalized).where(
            Transaction.account_id == source.account_id,
            Transaction.direction == source.direction,
            Transaction.type == source.type,
            Transaction.deleted_at.is_(None),
        )
    ).all()
    matching_ids = [
        candidate_id
        for candidate_id, description in candidates
        if descriptions_share_recipient(source.description_normalized, description)
    ]
    matches = list(
        session.scalars(
            select(Transaction).where(Transaction.id.in_(matching_ids)).with_for_update()
        )
    )
    updated_count = 0
    for transaction in matches:
        if transaction.category_id == category.id and transaction.is_reviewed:
            continue
        before_category = transaction.category_id
        before_reviewed = transaction.is_reviewed
        transaction.category_id = category.id
        transaction.classification_method = ClassificationMethod.MANUAL
        transaction.is_reviewed = True
        session.add(
            AuditEvent(
                aggregate_type="transaction",
                aggregate_id=transaction.id,
                action="similar_recipient_category_applied",
                changed_fields=["category_id", "is_reviewed"],
                change_data={
                    "category_id": {
                        "before": str(before_category) if before_category else None,
                        "after": str(category.id),
                    },
                    "is_reviewed": {"before": before_reviewed, "after": True},
                    "source_transaction_id": str(source.id),
                },
                actor_type=AuditActorType.USER,
                actor_identifier="local-user",
            )
        )
        updated_count += 1

    rule_created = False
    if request.create_rule:
        rule_pattern = recipient_rule_pattern(
            source.description_normalized,
            [transaction.description_normalized for transaction in matches],
        )
        rule = session.scalar(
            select(CategoryRule).where(
                CategoryRule.match_field == RuleMatchField.DESCRIPTION,
                CategoryRule.pattern == rule_pattern,
                CategoryRule.account_id == source.account_id,
                CategoryRule.is_active.is_(True),
            )
        )
        if rule is None:
            rule = CategoryRule(
                match_field=RuleMatchField.DESCRIPTION,
                pattern=rule_pattern,
                category_id=category.id,
                priority=1_000,
                account_id=source.account_id,
                hit_count=updated_count,
                origin=RuleOrigin.CONFIRMED_CORRECTION,
                is_active=True,
            )
            session.add(rule)
            session.flush()
            session.add(
                AuditEvent(
                    aggregate_type="category_rule",
                    aggregate_id=rule.id,
                    action="category_rule_created_from_correction",
                    changed_fields=[
                        "match_field",
                        "pattern",
                        "category_id",
                        "priority",
                        "account_id",
                    ],
                    actor_type=AuditActorType.USER,
                    actor_identifier="local-user",
                )
            )
            rule_created = True
        else:
            previous_category_id = rule.category_id
            previous_priority = rule.priority
            rule.category_id = category.id
            rule.priority = max(rule.priority, 1_000)
            rule.origin = RuleOrigin.CONFIRMED_CORRECTION
            rule.hit_count += updated_count
            session.add(
                AuditEvent(
                    aggregate_type="category_rule",
                    aggregate_id=rule.id,
                    action="category_rule_updated_from_correction",
                    changed_fields=["category_id", "priority", "origin", "hit_count"],
                    change_data={
                        "category_id": {
                            "before": str(previous_category_id),
                            "after": str(category.id),
                        },
                        "priority": {
                            "before": previous_priority,
                            "after": rule.priority,
                        },
                    },
                    actor_type=AuditActorType.USER,
                    actor_identifier="local-user",
                )
            )

    session.commit()
    return SimilarTransactionsCategoryResult(
        category_id=category.id,
        updated_count=updated_count,
        rule_created=rule_created,
    )


@router.post("/{transaction_id}/category/undo", response_model=TransactionRead)
def undo_last_category_change(
    transaction_id: UUID,
    session: DatabaseSession,
) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.deleted_at is not None:
        raise _not_found("transaction_not_found", "Transaction was not found")
    audit_events = list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.aggregate_type == "transaction",
                AuditEvent.aggregate_id == transaction.id,
                AuditEvent.action.in_(
                    ["transaction_updated", "similar_recipient_category_applied"]
                ),
                AuditEvent.change_data.has_key("category_id"),  # type: ignore[attr-defined]
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
    )
    current_value = str(transaction.category_id) if transaction.category_id else None
    audit_event = next(
        (
            event
            for event in audit_events
            if isinstance(event.change_data.get("category_id"), dict)
            and event.change_data["category_id"].get("after") == current_value
        ),
        None,
    )
    if audit_event is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "category_change_not_found",
                "message": "No category change can be undone",
            },
        )
    category_change = audit_event.change_data["category_id"]
    if not isinstance(category_change, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_audit_event", "message": "Category audit event is invalid"},
        )
    previous_value = category_change.get("before")
    previous_category_id = UUID(previous_value) if isinstance(previous_value, str) else None
    if previous_category_id is not None and session.get(Category, previous_category_id) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "previous_category_not_found",
                "message": "Previous category no longer exists",
            },
        )
    current_category_id = transaction.category_id
    transaction.category_id = previous_category_id
    transaction.classification_method = ClassificationMethod.MANUAL
    transaction.is_reviewed = True
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="transaction_category_change_reverted",
            changed_fields=["category_id"],
            change_data={
                "category_id": {
                    "before": str(current_category_id) if current_category_id else None,
                    "after": str(previous_category_id) if previous_category_id else None,
                },
                "reverted_audit_event_id": str(audit_event.id),
            },
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: UUID, session: DatabaseSession) -> None:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.deleted_at is not None:
        raise _not_found("transaction_not_found", "Transaction was not found")
    transaction.deleted_at = utc_now()
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="transaction_soft_deleted",
            changed_fields=["deleted_at"],
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
