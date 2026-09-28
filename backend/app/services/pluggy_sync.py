import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.integrations.pluggy import (
    BankDataProvider,
    ExternalAccount,
    ExternalItem,
    ExternalTransaction,
    PluggyAPIError,
)
from app.models.account import Account, BalanceSnapshot
from app.models.audit import AuditEvent
from app.models.category import CategoryRule
from app.models.enums import (
    AuditActorType,
    BalanceSnapshotSource,
    ClassificationMethod,
    SyncRunStatus,
    SyncTrigger,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.integration import (
    PluggyAccountLink,
    PluggyItem,
    PluggyTransactionLink,
    SyncRun,
)
from app.models.transaction import Transaction
from app.services.category_rules import CategoryRuleCandidate, RuleField, select_category_rule
from app.services.deduplication import normalize_description, transaction_deduplication_hash
from app.services.money import money, positive_money

USER_ACTION_STATUSES = {"LOGIN_ERROR", "WAITING_USER_INPUT"}
USER_ACTION_EXECUTION_STATUSES = {
    "INVALID_CREDENTIALS",
    "INVALID_CREDENTIALS_MFA",
    "USER_AUTHORIZATION_NOT_GRANTED",
    "USER_AUTHORIZATION_REVOKED",
    "USER_AUTHORIZATION_PENDING",
    "USER_INPUT_TIMEOUT",
    "ACCOUNT_LOCKED",
    "ACCOUNT_NEEDS_ACTION",
    "ACCOUNT_CREDENTIALS_RESET",
    "WAITING_USER_INPUT",
}
READY_EXECUTION_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS"}


@dataclass(frozen=True, slots=True)
class SyncCounts:
    created: int = 0
    updated: int = 0
    reconciled: int = 0
    ignored: int = 0

    def add(self, other: "SyncCounts") -> "SyncCounts":
        return SyncCounts(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            reconciled=self.reconciled + other.reconciled,
            ignored=self.ignored + other.ignored,
        )


def sanitize_provider_code(value: str | None, *, fallback: str) -> str:
    if not value:
        return fallback
    safe = "".join(char for char in value if char.isalnum() or char in "_-.")
    return (safe or fallback)[:120]


def _requires_user_action(item: ExternalItem) -> bool:
    return item.status in USER_ACTION_STATUSES or (
        item.execution_status in USER_ACTION_EXECUTION_STATUSES
    )


def _apply_item_state(local: PluggyItem, external: ExternalItem, observed_at: datetime) -> None:
    local.connector_id = external.connector_id
    local.connector_name = external.connector_name
    local.status = external.status
    local.execution_status = external.execution_status
    local.error_code = sanitize_provider_code(external.error_code, fallback="") or None
    local.requires_user_action = _requires_user_action(external)
    local.consent_expires_at = external.consent_expires_at
    local.provider_updated_at = external.updated_at
    local.last_polled_at = observed_at


def register_pluggy_item(
    session: Session,
    provider: BankDataProvider,
    *,
    external_item_id: str,
    poll_seconds: int,
) -> PluggyItem:
    external = provider.get_item(external_item_id)
    item = session.scalar(select(PluggyItem).where(PluggyItem.external_item_id == external_item_id))
    now = utc_now()
    if item is None:
        item = PluggyItem(
            external_item_id=external_item_id,
            status=external.status,
            consecutive_failures=0,
            is_active=True,
        )
        session.add(item)
        session.flush()
        session.add(
            AuditEvent(
                aggregate_type="pluggy_item",
                aggregate_id=item.id,
                action="pluggy_item_registered",
                changed_fields=["external_item_id", "status"],
                actor_type=AuditActorType.USER,
                actor_identifier="local-user",
            )
        )
    _apply_item_state(item, external, now)
    item.deleted_at = None
    item.is_active = True
    item.next_sync_at = now + timedelta(seconds=min(poll_seconds, 60))
    if external.status == "UPDATED" and external.execution_status in READY_EXECUTION_STATUSES:
        _upsert_external_accounts(session, item, provider.list_accounts(external_item_id), now)
    session.commit()
    session.refresh(item)
    return item


def _upsert_external_accounts(
    session: Session,
    item: PluggyItem,
    accounts: list[ExternalAccount],
    observed_at: datetime,
) -> list[PluggyAccountLink]:
    seen: set[str] = set()
    links: list[PluggyAccountLink] = []
    for external in accounts:
        seen.add(external.id)
        link = session.scalar(
            select(PluggyAccountLink).where(PluggyAccountLink.external_account_id == external.id)
        )
        if link is None:
            link = PluggyAccountLink(
                pluggy_item_id=item.id,
                external_account_id=external.id,
                name=external.name,
                account_type=external.type,
                subtype=external.subtype,
                currency_code=external.currency_code,
                balance=money(external.balance) if external.balance is not None else None,
                last_seen_at=observed_at,
                is_active=True,
            )
            session.add(link)
        else:
            link.pluggy_item_id = item.id
            link.name = external.name
            link.account_type = external.type
            link.subtype = external.subtype
            link.currency_code = external.currency_code
            link.balance = money(external.balance) if external.balance is not None else None
            link.last_seen_at = observed_at
            link.is_active = True
            link.deleted_at = None
        links.append(link)
    existing = session.scalars(
        select(PluggyAccountLink).where(
            PluggyAccountLink.pluggy_item_id == item.id,
            PluggyAccountLink.deleted_at.is_(None),
        )
    )
    for link in existing:
        if link.external_account_id not in seen:
            link.is_active = False
    session.flush()
    return links


def link_pluggy_account(
    session: Session,
    *,
    link_id: UUID,
    local_account_id: UUID,
) -> PluggyAccountLink:
    link = session.get(PluggyAccountLink, link_id)
    account = session.get(Account, local_account_id)
    if link is None or link.deleted_at is not None:
        raise LookupError("pluggy_account_not_found")
    if account is None or account.deleted_at is not None or not account.is_active:
        raise LookupError("account_not_found")
    if link.currency_code != account.currency_code:
        raise ValueError("account_currency_mismatch")
    existing = session.scalar(
        select(PluggyAccountLink).where(
            PluggyAccountLink.local_account_id == local_account_id,
            PluggyAccountLink.id != link.id,
            PluggyAccountLink.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise ValueError("account_already_linked")
    if account.pluggy_account_id not in {None, link.external_account_id}:
        raise ValueError("account_already_linked")
    link.local_account_id = local_account_id
    account.pluggy_account_id = link.external_account_id
    session.add(
        AuditEvent(
            aggregate_type="account",
            aggregate_id=account.id,
            action="pluggy_account_linked",
            changed_fields=["pluggy_account_id"],
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(link)
    return link


def queue_pluggy_sync(
    session: Session,
    *,
    item: PluggyItem,
    trigger: SyncTrigger,
    full_reconciliation: bool,
) -> SyncRun:
    existing = session.scalar(
        select(SyncRun)
        .where(
            SyncRun.integration == "pluggy",
            SyncRun.pluggy_item_id == item.id,
            SyncRun.status.in_([SyncRunStatus.PENDING, SyncRunStatus.RUNNING]),
        )
        .order_by(SyncRun.created_at)
    )
    if existing is not None:
        if full_reconciliation and existing.status == SyncRunStatus.PENDING:
            existing.full_reconciliation = True
            session.commit()
        return existing
    run = SyncRun(
        integration="pluggy",
        pluggy_item_id=item.id,
        status=SyncRunStatus.PENDING,
        trigger=trigger,
        full_reconciliation=full_reconciliation,
        cursor={},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def queue_manual_syncs(
    session: Session,
    *,
    item_id: UUID | None,
    full_reconciliation: bool,
) -> list[SyncRun]:
    statement = select(PluggyItem).where(
        PluggyItem.deleted_at.is_(None), PluggyItem.is_active.is_(True)
    )
    if item_id is not None:
        statement = statement.where(PluggyItem.id == item_id)
    items = list(session.scalars(statement.order_by(PluggyItem.created_at)))
    if item_id is not None and not items:
        raise LookupError("pluggy_item_not_found")
    return [
        queue_pluggy_sync(
            session,
            item=item,
            trigger=SyncTrigger.MANUAL,
            full_reconciliation=full_reconciliation,
        )
        for item in items
    ]


def _rule_candidates(
    session: Session,
) -> tuple[list[CategoryRuleCandidate], dict[UUID, CategoryRule]]:
    models = list(session.scalars(select(CategoryRule).where(CategoryRule.is_active.is_(True))))
    by_id = {model.id: model for model in models}
    return (
        [
            CategoryRuleCandidate(
                id=model.id,
                category_id=model.category_id,
                pattern=model.pattern,
                priority=model.priority,
                match_field=RuleField(model.match_field.value),
                account_id=model.account_id,
                active=model.is_active,
            )
            for model in models
        ],
        by_id,
    )


def _transaction_values(
    external: ExternalTransaction,
    *,
    account_id: UUID,
    timezone: str,
) -> dict[str, object] | None:
    direction_value = external.type
    if direction_value not in {"CREDIT", "DEBIT"}:
        if external.amount > 0:
            direction_value = "CREDIT"
        elif external.amount < 0:
            direction_value = "DEBIT"
        else:
            return None
    try:
        amount = positive_money(abs(external.amount))
    except (TypeError, ValueError):
        return None
    direction = (
        TransactionDirection.CREDIT if direction_value == "CREDIT" else TransactionDirection.DEBIT
    )
    transaction_type = (
        TransactionType.INCOME
        if direction == TransactionDirection.CREDIT
        else TransactionType.EXPENSE
    )
    status = TransactionStatus.PENDING if external.status == "PENDING" else TransactionStatus.POSTED
    description = external.description_raw or external.description
    transaction_date = external.date.astimezone(ZoneInfo(timezone)).date()
    normalized = normalize_description(description)
    deduplication_hash = transaction_deduplication_hash(
        account_id=account_id,
        transaction_date=transaction_date,
        description=description,
        amount=amount,
        direction=direction.value,
    )
    return {
        "type": transaction_type,
        "direction": direction,
        "status": status,
        "amount": amount,
        "transaction_date": transaction_date,
        "posted_at": external.date,
        "description_raw": description,
        "description_normalized": normalized,
        "merchant_name": external.merchant_name,
        "deduplication_hash": deduplication_hash,
    }


def _payload_hash(external: ExternalTransaction) -> str:
    canonical = json.dumps(
        {
            "id": external.id,
            "account_id": external.account_id,
            "description": external.description,
            "description_raw": external.description_raw,
            "amount": format(external.amount, "f"),
            "currency": external.currency_code,
            "date": external.date.astimezone(UTC).isoformat(),
            "type": external.type,
            "status": external.status,
            "merchant": external.merchant_name,
            "category": external.provider_category,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _update_transaction(transaction: Transaction, values: dict[str, object]) -> list[str]:
    changed: list[str] = []
    for field, value in values.items():
        if getattr(transaction, field) != value:
            setattr(transaction, field, value)
            changed.append(field)
    return changed


def _sync_external_transaction(
    session: Session,
    *,
    link: PluggyAccountLink,
    external: ExternalTransaction,
    timezone: str,
    observed_at: datetime,
    rules: list[CategoryRuleCandidate],
    rule_models: dict[UUID, CategoryRule],
) -> SyncCounts:
    if (
        link.local_account_id is None
        or external.currency_code != link.currency_code
        or external.account_id != link.external_account_id
    ):
        return SyncCounts(ignored=1)
    values = _transaction_values(
        external,
        account_id=link.local_account_id,
        timezone=timezone,
    )
    if values is None:
        return SyncCounts(ignored=1)
    provider_hash = _payload_hash(external)
    external_link = session.scalar(
        select(PluggyTransactionLink).where(
            PluggyTransactionLink.pluggy_account_link_id == link.id,
            PluggyTransactionLink.external_transaction_id == external.id,
        )
    )
    if external_link is not None:
        transaction = session.get(Transaction, external_link.transaction_id)
        if transaction is None:
            return SyncCounts(ignored=1)
        if not external_link.provider_managed:
            external_link.payload_hash = provider_hash
            external_link.last_seen_at = observed_at
            return SyncCounts(ignored=1)
        changed = _update_transaction(transaction, values)
        external_link.payload_hash = provider_hash
        external_link.last_seen_at = observed_at
        if changed:
            session.add(
                AuditEvent(
                    aggregate_type="transaction",
                    aggregate_id=transaction.id,
                    action="pluggy_transaction_updated",
                    changed_fields=changed,
                    actor_type=AuditActorType.SERVICE,
                    actor_identifier="finance-worker",
                )
            )
            return SyncCounts(updated=1)
        return SyncCounts(ignored=1)

    transaction = session.scalar(
        select(Transaction)
        .where(
            Transaction.account_id == link.local_account_id,
            Transaction.deduplication_hash == values["deduplication_hash"],
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.created_at, Transaction.id)
        .limit(1)
    )
    reconciled = transaction is not None
    changed_fields = ["external_transaction_id"]
    if transaction is None:
        rule = select_category_rule(
            description=str(values["description_raw"]),
            account_id=link.local_account_id,
            rules=rules,
            merchant_name=external.merchant_name,
            external_id=external.id,
        )
        if rule is not None:
            rule_models[rule.id].hit_count += 1
        transaction = Transaction(
            account_id=link.local_account_id,
            category_id=rule.category_id if rule is not None else None,
            source=TransactionSource.PLUGGY,
            external_id=external.id,
            classification_method=(
                ClassificationMethod.RULE if rule is not None else ClassificationMethod.PLUGGY
            ),
            classification_confidence=None,
            is_reviewed=False,
            notes=None,
            transfer_group_id=None,
            **values,
        )
        session.add(transaction)
        session.flush()
        action = "pluggy_transaction_created"
    else:
        action = "pluggy_transaction_reconciled"
    session.add(
        PluggyTransactionLink(
            pluggy_account_link_id=link.id,
            transaction_id=transaction.id,
            external_transaction_id=external.id,
            provider_managed=not reconciled,
            payload_hash=provider_hash,
            last_seen_at=observed_at,
        )
    )
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action=action,
            changed_fields=changed_fields,
            actor_type=AuditActorType.SERVICE,
            actor_identifier="finance-worker",
        )
    )
    return SyncCounts(reconciled=1) if reconciled else SyncCounts(created=1)


def _store_balance_snapshot(
    session: Session,
    *,
    link: PluggyAccountLink,
    observed_at: datetime,
) -> None:
    if link.local_account_id is None or link.balance is None:
        return
    external_id = f"{link.external_account_id}:{observed_at.isoformat()}"
    exists = session.scalar(
        select(BalanceSnapshot.id).where(
            BalanceSnapshot.account_id == link.local_account_id,
            BalanceSnapshot.source == BalanceSnapshotSource.PLUGGY,
            BalanceSnapshot.external_id == external_id,
        )
    )
    if exists is None:
        session.add(
            BalanceSnapshot(
                account_id=link.local_account_id,
                amount=money(link.balance),
                currency_code=link.currency_code,
                source=BalanceSnapshotSource.PLUGGY,
                observed_at=observed_at,
                external_id=external_id,
            )
        )


def _run_sync(
    session: Session,
    provider: BankDataProvider,
    *,
    run: SyncRun,
    item: PluggyItem,
    timezone: str,
    poll_seconds: int,
    full_sync_seconds: int,
    max_attempts: int,
) -> SyncRun:
    started_at = utc_now()
    run.status = SyncRunStatus.RUNNING
    run.started_at = started_at
    run.error_code = None
    session.commit()
    try:
        external_item = provider.get_item(item.external_item_id)
        _apply_item_state(item, external_item, started_at)
        accounts = provider.list_accounts(item.external_item_id)
        links = _upsert_external_accounts(session, item, accounts, started_at)
        run.accounts_consulted = len(accounts)
        session.flush()
        if (
            external_item.status != "UPDATED"
            or external_item.execution_status not in READY_EXECUTION_STATUSES
        ):
            code = (
                external_item.error_code or external_item.execution_status or external_item.status
            )
            run.status = SyncRunStatus.PARTIAL
            run.error_code = sanitize_provider_code(code, fallback="pluggy_item_not_ready")
            run.finished_at = utc_now()
            item.next_sync_at = started_at + timedelta(seconds=min(poll_seconds, 60))
            session.commit()
            return run

        rules, rule_models = _rule_candidates(session)
        counts = SyncCounts()
        for link in links:
            if link.local_account_id is None or not link.is_active:
                counts = counts.add(SyncCounts(ignored=1))
                continue
            balance_time = external_item.updated_at or started_at
            _store_balance_snapshot(session, link=link, observed_at=balance_time)
            created_at_from = None
            if not run.full_reconciliation and item.last_successful_sync_at is not None:
                created_at_from = item.last_successful_sync_at - timedelta(days=2)
            cursor: str | None = None
            while True:
                page = provider.list_transactions(
                    link.external_account_id,
                    cursor=cursor,
                    created_at_from=created_at_from if cursor is None else None,
                )
                for external in page.transactions:
                    counts = counts.add(
                        _sync_external_transaction(
                            session,
                            link=link,
                            external=external,
                            timezone=timezone,
                            observed_at=started_at,
                            rules=rules,
                            rule_models=rule_models,
                        )
                    )
                cursor = page.next_cursor
                run.cursor = {
                    "account_id": link.external_account_id,
                    "next": cursor or "",
                }
                session.flush()
                if cursor is None:
                    break
        run.created_count = counts.created
        run.updated_count = counts.updated
        run.reconciled_count = counts.reconciled
        run.ignored_count = counts.ignored
        run.status = (
            SyncRunStatus.PARTIAL
            if external_item.execution_status == "PARTIAL_SUCCESS"
            else SyncRunStatus.SUCCESS
        )
        run.error_code = (
            "pluggy_partial_success"
            if external_item.execution_status == "PARTIAL_SUCCESS"
            else None
        )
        run.finished_at = utc_now()
        item.last_successful_sync_at = run.finished_at
        if run.full_reconciliation:
            item.last_full_sync_at = run.finished_at
        item.next_sync_at = started_at + timedelta(seconds=poll_seconds)
        item.consecutive_failures = 0
        session.commit()
        return run
    except PluggyAPIError as exc:
        session.rollback()
        run = session.get(SyncRun, run.id)
        item = session.get(PluggyItem, item.id)
        if run is None or item is None:
            raise
        item.consecutive_failures += 1
        retry_delay = exc.retry_after_seconds or min(
            poll_seconds,
            30 * (2 ** min(item.consecutive_failures - 1, max_attempts - 1)),
        )
        item.next_sync_at = utc_now() + timedelta(seconds=retry_delay)
        run.status = SyncRunStatus.FAILED
        run.error_code = exc.code
        run.finished_at = utc_now()
        session.commit()
        return run
    except (IntegrityError, ValueError):
        session.rollback()
        run = session.get(SyncRun, run.id)
        item = session.get(PluggyItem, item.id)
        if run is None or item is None:
            raise
        item.consecutive_failures += 1
        item.next_sync_at = utc_now() + timedelta(seconds=poll_seconds)
        run.status = SyncRunStatus.FAILED
        run.error_code = "pluggy_reconciliation_failed"
        run.finished_at = utc_now()
        session.commit()
        return run


def process_next_pluggy_job(
    session: Session,
    provider: BankDataProvider,
    *,
    timezone: str,
    poll_seconds: int,
    full_sync_seconds: int,
    max_attempts: int,
) -> SyncRun | None:
    run = session.scalar(
        select(SyncRun)
        .where(
            SyncRun.integration == "pluggy",
            SyncRun.status == SyncRunStatus.PENDING,
        )
        .order_by(SyncRun.created_at, SyncRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        now = utc_now()
        item = session.scalar(
            select(PluggyItem)
            .where(
                PluggyItem.deleted_at.is_(None),
                PluggyItem.is_active.is_(True),
                PluggyItem.requires_user_action.is_(False),
                or_(PluggyItem.next_sync_at.is_(None), PluggyItem.next_sync_at <= now),
            )
            .order_by(PluggyItem.next_sync_at.asc().nullsfirst(), PluggyItem.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if item is None:
            session.rollback()
            return None
        full = item.last_full_sync_at is None or item.last_full_sync_at <= now - timedelta(
            seconds=full_sync_seconds
        )
        run = SyncRun(
            integration="pluggy",
            pluggy_item_id=item.id,
            status=SyncRunStatus.PENDING,
            trigger=SyncTrigger.SCHEDULED,
            full_reconciliation=full,
            cursor={},
        )
        session.add(run)
        session.commit()
        session.refresh(run)
    item = session.get(PluggyItem, run.pluggy_item_id)
    if item is None or item.deleted_at is not None or not item.is_active:
        run.status = SyncRunStatus.FAILED
        run.error_code = "pluggy_item_unavailable"
        run.finished_at = utc_now()
        session.commit()
        return run
    return _run_sync(
        session,
        provider,
        run=run,
        item=item,
        timezone=timezone,
        poll_seconds=poll_seconds,
        full_sync_seconds=full_sync_seconds,
        max_attempts=max_attempts,
    )
