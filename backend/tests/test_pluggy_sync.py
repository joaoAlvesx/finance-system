import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from alembic import command
from app.integrations.pluggy import (
    ExternalAccount,
    ExternalItem,
    ExternalTransaction,
    PluggyAPIError,
    TransactionPage,
)
from app.models.account import Account, BalanceSnapshot
from app.models.audit import AuditEvent
from app.models.enums import (
    AccountType,
    BalanceSnapshotSource,
    ClassificationMethod,
    SyncRunStatus,
    SyncTrigger,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.integration import PluggyAccountLink, PluggyTransactionLink
from app.models.transaction import Transaction
from app.services.deduplication import normalize_description, transaction_deduplication_hash
from app.services.pluggy_sync import (
    link_pluggy_account,
    process_next_pluggy_job,
    queue_pluggy_sync,
    register_pluggy_item,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def postgres_session() -> Session:
    database_url = os.environ.get("FINANCE_DATABASE_URL")
    if not database_url or not database_url.partition("?")[0].endswith("_test"):
        pytest.skip("an isolated database ending in _test is required")
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
        engine.dispose()


class FakePluggyProvider:
    def __init__(self) -> None:
        self.item = ExternalItem(
            id="item-1",
            connector_id=200,
            connector_name="Meu Pluggy",
            status="UPDATED",
            execution_status="SUCCESS",
            error_code=None,
            consent_expires_at=None,
            updated_at=datetime(2026, 9, 15, 12, tzinfo=UTC),
        )
        self.account = ExternalAccount(
            id="external-account-1",
            item_id="item-1",
            name="Conta corrente Pluggy",
            type="BANK",
            subtype="CHECKING_ACCOUNT",
            currency_code="BRL",
            balance=Decimal("500.00"),
        )
        self.transactions = [
            ExternalTransaction(
                id="external-transaction-1",
                account_id=self.account.id,
                description="Mercado Central",
                description_raw=None,
                amount=Decimal("-25.00"),
                currency_code="BRL",
                date=datetime(2026, 9, 14, 15, tzinfo=UTC),
                type="DEBIT",
                status="POSTED",
                merchant_name="Mercado Central",
                provider_category="Groceries",
            ),
            ExternalTransaction(
                id="external-transaction-2",
                account_id=self.account.id,
                description="Restaurante Universitário",
                description_raw=None,
                amount=Decimal("-14.50"),
                currency_code="BRL",
                date=datetime(2026, 9, 15, 16, tzinfo=UTC),
                type="DEBIT",
                status="PENDING",
                merchant_name="PaladarNutri",
                provider_category="Eating out",
            ),
        ]
        self.fail_with: PluggyAPIError | None = None
        self.account_calls = 0
        self.transaction_calls: list[tuple[str | None, datetime | None]] = []

    def create_connect_token(self, *, client_user_id: str, item_id: str | None = None) -> str:
        return "fake-connect-token"

    def get_item(self, item_id: str) -> ExternalItem:
        if self.fail_with:
            raise self.fail_with
        return self.item

    def trigger_item_update(self, item_id: str) -> None:
        return None

    def list_accounts(self, item_id: str) -> list[ExternalAccount]:
        self.account_calls += 1
        return [self.account]

    def list_transactions(
        self,
        account_id: str,
        *,
        cursor: str | None = None,
        created_at_from: datetime | None = None,
    ) -> TransactionPage:
        self.transaction_calls.append((cursor, created_at_from))
        if cursor is None:
            return TransactionPage(
                transactions=[self.transactions[0]],
                next_cursor="?accountId=external-account-1&after=next-page",
            )
        return TransactionPage(transactions=[self.transactions[1]], next_cursor=None)


def create_local_account_and_csv_transaction(session: Session) -> tuple[Account, Transaction]:
    account = Account(
        name="Conta Inter existente",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=Decimal("0.00"),
        is_active=True,
    )
    session.add(account)
    session.flush()
    deduplication_hash = transaction_deduplication_hash(
        account_id=account.id,
        transaction_date=datetime(2026, 9, 14).date(),
        description="Mercado Central",
        amount=Decimal("25.00"),
        direction="debit",
    )
    transaction = Transaction(
        account_id=account.id,
        type=TransactionType.EXPENSE,
        direction=TransactionDirection.DEBIT,
        status=TransactionStatus.POSTED,
        amount=Decimal("25.00"),
        transaction_date=datetime(2026, 9, 14).date(),
        posted_at=None,
        description_raw="Mercado Central",
        description_normalized=normalize_description("Mercado Central"),
        merchant_name=None,
        category_id=None,
        source=TransactionSource.CSV,
        external_id=None,
        source_file_id=None,
        classification_confidence=None,
        classification_method=ClassificationMethod.MANUAL,
        is_reviewed=False,
        notes=None,
        deduplication_hash=deduplication_hash,
        transfer_group_id=None,
    )
    session.add(transaction)
    session.commit()
    return account, transaction


@pytest.mark.migration
def test_pluggy_item_is_registered_while_provider_is_still_processing(
    postgres_session: Session,
) -> None:
    provider = FakePluggyProvider()
    provider.item = replace(
        provider.item,
        status="UPDATING",
        execution_status=None,
    )

    item = register_pluggy_item(
        postgres_session,
        provider,
        external_item_id="item-1",
        poll_seconds=900,
    )

    assert item.status == "UPDATING"
    assert provider.account_calls == 0
    assert postgres_session.scalar(select(func.count(PluggyAccountLink.id))) == 0


@pytest.mark.migration
def test_pluggy_sync_reconciles_csv_and_is_idempotent(postgres_session: Session) -> None:
    account, csv_transaction = create_local_account_and_csv_transaction(postgres_session)
    provider = FakePluggyProvider()
    item = register_pluggy_item(
        postgres_session,
        provider,
        external_item_id="item-1",
        poll_seconds=900,
    )
    link = postgres_session.scalar(
        select(PluggyAccountLink).where(PluggyAccountLink.pluggy_item_id == item.id)
    )
    assert link is not None
    link_pluggy_account(
        postgres_session,
        link_id=link.id,
        local_account_id=account.id,
    )

    queue_pluggy_sync(
        postgres_session,
        item=item,
        trigger=SyncTrigger.MANUAL,
        full_reconciliation=True,
    )
    first = process_next_pluggy_job(
        postgres_session,
        provider,
        timezone="America/Campo_Grande",
        poll_seconds=900,
        full_sync_seconds=86400,
        max_attempts=5,
    )
    assert first is not None
    assert first.status == SyncRunStatus.SUCCESS
    assert (first.created_count, first.reconciled_count, first.updated_count) == (1, 1, 0)
    assert provider.transaction_calls[0] == (None, None)
    assert provider.transaction_calls[1][0] is not None
    assert postgres_session.scalar(select(func.count(Transaction.id))) == 2
    assert postgres_session.scalar(select(func.count(PluggyTransactionLink.id))) == 2
    transaction_links = {
        external_link.external_transaction_id: external_link
        for external_link in postgres_session.scalars(select(PluggyTransactionLink))
    }
    assert transaction_links["external-transaction-1"].transaction_id == csv_transaction.id
    assert transaction_links["external-transaction-1"].provider_managed is False
    assert transaction_links["external-transaction-2"].transaction_id != csv_transaction.id
    assert transaction_links["external-transaction-2"].provider_managed is True
    assert (
        postgres_session.scalar(
            select(func.count(BalanceSnapshot.id)).where(
                BalanceSnapshot.source == BalanceSnapshotSource.PLUGGY
            )
        )
        == 1
    )
    postgres_session.refresh(csv_transaction)
    assert csv_transaction.source == TransactionSource.CSV
    assert csv_transaction.external_id is None

    second_run = queue_pluggy_sync(
        postgres_session,
        item=item,
        trigger=SyncTrigger.MANUAL,
        full_reconciliation=True,
    )
    second = process_next_pluggy_job(
        postgres_session,
        provider,
        timezone="America/Campo_Grande",
        poll_seconds=900,
        full_sync_seconds=86400,
        max_attempts=5,
    )
    assert second is not None and second.id == second_run.id
    unexpected_updates = list(
        postgres_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "pluggy_transaction_updated")
        )
    )
    assert (second.created_count, second.reconciled_count, second.updated_count) == (0, 0, 0), (
        [(str(event.aggregate_id), event.changed_fields) for event in unexpected_updates],
        str(csv_transaction.id),
    )
    assert second.ignored_count == 2
    assert postgres_session.scalar(select(func.count(Transaction.id))) == 2
    assert (
        postgres_session.scalar(
            select(func.count(BalanceSnapshot.id)).where(
                BalanceSnapshot.source == BalanceSnapshotSource.PLUGGY
            )
        )
        == 1
    )

    provider.transactions[1] = replace(
        provider.transactions[1],
        description="Restaurante Universitário atualizado",
        status="POSTED",
    )
    queue_pluggy_sync(
        postgres_session,
        item=item,
        trigger=SyncTrigger.MANUAL,
        full_reconciliation=True,
    )
    third = process_next_pluggy_job(
        postgres_session,
        provider,
        timezone="America/Campo_Grande",
        poll_seconds=900,
        full_sync_seconds=86400,
        max_attempts=5,
    )
    assert third is not None
    assert third.updated_count == 1
    updated = postgres_session.scalar(
        select(Transaction).where(Transaction.external_id == "external-transaction-2")
    )
    assert updated is not None
    assert updated.description_raw == "Restaurante Universitário atualizado"
    assert updated.status == TransactionStatus.POSTED


@pytest.mark.migration
def test_pluggy_consent_failure_and_retry_are_sanitized(postgres_session: Session) -> None:
    account, _ = create_local_account_and_csv_transaction(postgres_session)
    provider = FakePluggyProvider()
    item = register_pluggy_item(
        postgres_session,
        provider,
        external_item_id="item-1",
        poll_seconds=900,
    )
    link = postgres_session.scalar(select(PluggyAccountLink))
    assert link is not None
    link_pluggy_account(postgres_session, link_id=link.id, local_account_id=account.id)
    provider.item = replace(
        provider.item,
        status="LOGIN_ERROR",
        execution_status="USER_AUTHORIZATION_REVOKED",
        error_code="USER_AUTHORIZATION_REVOKED",
    )
    queue_pluggy_sync(
        postgres_session,
        item=item,
        trigger=SyncTrigger.MANUAL,
        full_reconciliation=False,
    )
    consent_run = process_next_pluggy_job(
        postgres_session,
        provider,
        timezone="America/Campo_Grande",
        poll_seconds=900,
        full_sync_seconds=86400,
        max_attempts=5,
    )
    assert consent_run is not None
    assert consent_run.status == SyncRunStatus.PARTIAL
    postgres_session.refresh(item)
    assert item.requires_user_action is True
    assert item.error_code == "USER_AUTHORIZATION_REVOKED"

    item.requires_user_action = False
    provider.fail_with = PluggyAPIError("pluggy_http_429", retryable=True, retry_after_seconds=60)
    queue_pluggy_sync(
        postgres_session,
        item=item,
        trigger=SyncTrigger.MANUAL,
        full_reconciliation=False,
    )
    failed = process_next_pluggy_job(
        postgres_session,
        provider,
        timezone="America/Campo_Grande",
        poll_seconds=900,
        full_sync_seconds=86400,
        max_attempts=5,
    )
    assert failed is not None
    assert failed.status == SyncRunStatus.FAILED
    assert failed.error_code == "pluggy_http_429"
    postgres_session.refresh(item)
    assert item.consecutive_failures == 1
    assert item.next_sync_at is not None
