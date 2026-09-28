import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from alembic import command
from app.api.routes.categories import create_category as create_category_route
from app.api.routes.dashboard import get_dashboard
from app.api.routes.planning import (
    create_expected_income,
    create_planned_expense,
    update_budget_settings,
)
from app.api.routes.transactions import (
    apply_category_to_similar_transactions,
    create_transaction,
    undo_last_category_change,
    update_transaction,
)
from app.integrations.telegram import TelegramAPIError, TelegramUpdate
from app.models.account import Account, BalanceSnapshot
from app.models.audit import AuditEvent
from app.models.category import Category, CategoryRule
from app.models.enums import (
    AccountType,
    AuditActorType,
    BalanceSnapshotSource,
    CategoryKind,
    ImportRowStatus,
    ImportStatus,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.importing import ImportRow
from app.models.integration import IntegrationCheckpoint, NotificationLog
from app.models.transaction import Transaction
from app.schemas.categories import CategoryCreate
from app.schemas.planning import (
    BudgetSettingsUpdate,
    ExpectedIncomeCreate,
    PlannedExpenseCreate,
)
from app.schemas.transactions import (
    SimilarTransactionsCategoryUpdate,
    TransactionCreate,
    TransactionPatch,
)
from app.services.dashboard import default_budget_settings, local_today
from app.services.imports import confirm_csv_import, preview_csv_import
from app.services.telegram_notifications import (
    dispatch_notifications,
    initialize_expense_checkpoint,
    process_telegram_updates,
    scan_new_expenses,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def inter_csv(*rows: str) -> bytes:
    lines = [
        "Extrato Conta Corrente;",
        "Conta;DADOS OMITIDOS",
        "Período;01/01/2026 a 31/01/2026",
        ";",
        ";",
        "Data Lançamento;Histórico;Descrição;Valor;Saldo",
        *rows,
    ]
    return ("\ufeff" + "\n".join(lines)).encode()


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


@pytest.mark.migration
def test_preview_confirm_idempotence_overlap_and_rollback(postgres_session: Session) -> None:
    account = Account(
        name="Conta de teste",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=0,
        is_active=True,
    )
    postgres_session.add(account)
    postgres_session.flush()

    first_content = inter_csv(
        "10/01/2026;Compra no débito;UBER TESTE;- 20,00;980,00",
        "09/01/2026;Pix recebido;PESSOA TESTE;1.000,00;1.000,00",
        "data ruim;Pix enviado;PESSOA TESTE;- 10,00;990,00",
    )
    first = preview_csv_import(
        postgres_session,
        account_id=account.id,
        filename="primeiro.csv",
        content=first_content,
    )
    postgres_session.flush()

    assert first.status == ImportStatus.PREVIEWED
    assert (first.valid_rows, first.duplicate_rows, first.invalid_rows) == (2, 0, 1)
    preview_rows = list(
        postgres_session.scalars(
            select(ImportRow)
            .where(ImportRow.import_file_id == first.id)
            .order_by(ImportRow.row_number)
        )
    )
    category_names = {
        postgres_session.get(Category, row.suggested_category_id).name
        for row in preview_rows
        if row.suggested_category_id
    }
    assert {"Uber", "Pix"} <= category_names
    assert preview_rows[-1].status == ImportRowStatus.INVALID

    confirmed = confirm_csv_import(postgres_session, import_id=first.id)
    assert confirmed.status == ImportStatus.IMPORTED
    assert confirmed.imported_rows == 2
    assert postgres_session.scalar(select(func.count(Transaction.id))) == 2
    assert postgres_session.scalar(select(func.count(BalanceSnapshot.id))) == 1

    same_file = preview_csv_import(
        postgres_session,
        account_id=account.id,
        filename="renomeado.csv",
        content=first_content,
    )
    assert same_file.id == first.id
    confirm_csv_import(postgres_session, import_id=first.id)
    assert postgres_session.scalar(select(func.count(Transaction.id))) == 2

    overlap = preview_csv_import(
        postgres_session,
        account_id=account.id,
        filename="sobreposto.csv",
        content=inter_csv(
            "10/01/2026;Compra no débito;UBER TESTE;- 20,00;980,00",
            "11/01/2026;Compra no débito;MERCADO TESTE;- 30,00;950,00",
        ),
    )
    assert (overlap.valid_rows, overlap.duplicate_rows) == (1, 1)
    confirm_csv_import(postgres_session, import_id=overlap.id)
    assert postgres_session.scalar(select(func.count(Transaction.id))) == 3

    rollback_preview = preview_csv_import(
        postgres_session,
        account_id=account.id,
        filename="rollback.csv",
        content=inter_csv(
            "12/01/2026;Compra no débito;PADARIA TESTE;- 15,00;935,00",
        ),
    )
    postgres_session.flush()
    savepoint = postgres_session.begin_nested()
    confirm_csv_import(postgres_session, import_id=rollback_preview.id)
    assert rollback_preview.status == ImportStatus.IMPORTED
    savepoint.rollback()
    postgres_session.expire_all()
    restored = postgres_session.get(type(rollback_preview), rollback_preview.id)
    assert restored.status == ImportStatus.PREVIEWED
    assert (
        postgres_session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.source_file_id == rollback_preview.id
            )
        )
        == 0
    )


@pytest.mark.migration
def test_manual_category_changes_can_be_undone_in_order(postgres_session: Session) -> None:
    account = Account(
        name="Conta para categorias",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=0,
        is_active=True,
    )
    postgres_session.add(account)
    postgres_session.flush()
    categories = {
        category.name: category
        for category in postgres_session.scalars(
            select(Category).where(Category.name.in_(["Mercado", "Uber", "Alimentação"]))
        )
    }
    transaction = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="10.00",
            transaction_date="2026-01-10",
            description="Compra de teste",
            category_id=categories["Mercado"].id,
        ),
        postgres_session,
    )
    update_transaction(
        transaction.id,
        TransactionPatch(category_id=categories["Uber"].id),
        postgres_session,
    )
    update_transaction(
        transaction.id,
        TransactionPatch(category_id=categories["Alimentação"].id),
        postgres_session,
    )

    first_undo = undo_last_category_change(transaction.id, postgres_session)
    assert first_undo.category_id == categories["Uber"].id
    second_undo = undo_last_category_change(transaction.id, postgres_session)
    assert second_undo.category_id == categories["Mercado"].id


@pytest.mark.migration
def test_category_creation_is_trimmed_unique_and_audited(postgres_session: Session) -> None:
    created = create_category_route(
        CategoryCreate(
            name="  Restaurante universitário  ",
            kind=CategoryKind.EXPENSE,
            color="#46dea8",
        ),
        postgres_session,
    )

    assert created.name == "Restaurante universitário"
    audit = postgres_session.scalar(
        select(AuditEvent).where(
            AuditEvent.aggregate_type == "category",
            AuditEvent.aggregate_id == created.id,
            AuditEvent.action == "category_created",
            AuditEvent.actor_type == AuditActorType.USER,
        )
    )
    assert audit is not None

    with pytest.raises(HTTPException) as duplicate:
        create_category_route(
            CategoryCreate(
                name="restaurante universitário",
                kind=CategoryKind.EXPENSE,
            ),
            postgres_session,
        )
    assert duplicate.value.status_code == 409


@pytest.mark.migration
def test_category_can_be_applied_to_same_recipient_and_learned(
    postgres_session: Session,
) -> None:
    account = Account(
        name="Conta para agrupamento",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=0,
        is_active=True,
    )
    postgres_session.add(account)
    postgres_session.flush()
    categories = {
        category.name: category
        for category in postgres_session.scalars(
            select(Category).where(Category.name.in_(["Mercado", "Alimentação", "Renda"]))
        )
    }
    first = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="12.00",
            transaction_date="2026-01-10",
            description="Compra no débito — PALADARNUTRI BOA VISTA BRA",
            category_id=categories["Mercado"].id,
        ),
        postgres_session,
    )
    second = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="15.00",
            transaction_date="2026-01-11",
            description="Pix enviado — PaladarNutri",
            category_id=categories["Mercado"].id,
        ),
        postgres_session,
    )
    legal_suffix = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="16.00",
            transaction_date="2026-01-12",
            description="Pix enviado — PaladarNutri Ltda",
            category_id=categories["Mercado"].id,
        ),
        postgres_session,
    )
    opposite_direction = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.INCOME,
            direction=TransactionDirection.CREDIT,
            amount="15.00",
            transaction_date="2026-01-13",
            description="Pix recebido — PaladarNutri",
            category_id=categories["Renda"].id,
        ),
        postgres_session,
    )

    result = apply_category_to_similar_transactions(
        first.id,
        SimilarTransactionsCategoryUpdate(category_id=categories["Alimentação"].id),
        postgres_session,
    )

    assert result.updated_count == 3
    assert result.rule_created is True
    postgres_session.refresh(first)
    postgres_session.refresh(second)
    postgres_session.refresh(legal_suffix)
    postgres_session.refresh(opposite_direction)
    assert first.category_id == categories["Alimentação"].id
    assert second.category_id == categories["Alimentação"].id
    assert legal_suffix.category_id == categories["Alimentação"].id
    assert opposite_direction.category_id == categories["Renda"].id
    assert first.is_reviewed and second.is_reviewed

    rule = postgres_session.scalar(
        select(CategoryRule).where(
            CategoryRule.pattern == "paladarnutri",
            CategoryRule.account_id == account.id,
        )
    )
    assert rule is not None
    assert rule.category_id == categories["Alimentação"].id
    assert rule.priority == 1_000
    assert (
        postgres_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "similar_recipient_category_applied"
            )
        )
        == 3
    )

    preview = preview_csv_import(
        postgres_session,
        account_id=account.id,
        filename="regra-aprendida.csv",
        content=inter_csv("14/01/2026;Compra no débito;PALADARNUTRI NOVA FILIAL;- 18,00;100,00"),
    )
    preview_row = postgres_session.scalar(
        select(ImportRow).where(ImportRow.import_file_id == preview.id)
    )
    assert preview_row is not None
    assert preview_row.suggested_category_id == categories["Alimentação"].id

    reverted = undo_last_category_change(second.id, postgres_session)
    assert reverted.category_id == categories["Mercado"].id


class FakeTelegramGateway:
    def __init__(self, updates: list[TelegramUpdate] | None = None) -> None:
        self.updates = updates or []
        self.sent: list[tuple[str, str]] = []
        self.offsets: list[int | None] = []

    def send_message(self, *, chat_id: str, text: str) -> str:
        self.sent.append((chat_id, text))
        return str(len(self.sent))

    def get_updates(self, *, offset: int | None, timeout: int) -> list[TelegramUpdate]:
        self.offsets.append(offset)
        return [update for update in self.updates if offset is None or update.update_id >= offset]


class FailingTelegramGateway(FakeTelegramGateway):
    def send_message(self, *, chat_id: str, text: str) -> str:
        raise TelegramAPIError("telegram_unavailable")


@pytest.mark.migration
def test_telegram_alerts_are_idempotent_and_retry_is_limited(
    postgres_session: Session,
) -> None:
    account = Account(
        name="Conta Telegram",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=Decimal("100.00"),
        is_active=True,
    )
    postgres_session.add(account)
    postgres_session.flush()
    initialize_expense_checkpoint(postgres_session)
    settings = default_budget_settings(postgres_session)
    settings.telegram_notifications_enabled = True
    postgres_session.commit()

    expense = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="12.50",
            transaction_date="2026-09-15",
            description="Compra no débito — TESTE\nCOM CONTROLE",
        ),
        postgres_session,
    )
    assert scan_new_expenses(postgres_session) == 1
    assert scan_new_expenses(postgres_session) == 0

    gateway = FakeTelegramGateway()
    assert dispatch_notifications(
        postgres_session,
        gateway,
        chat_id="123456",
        max_attempts=3,
    ) == (1, 0)
    assert dispatch_notifications(
        postgres_session,
        gateway,
        chat_id="123456",
        max_attempts=3,
    ) == (0, 0)
    assert len(gateway.sent) == 1
    assert "R$ 12,50" in gateway.sent[0][1]
    assert "teste com controle" in gateway.sent[0][1]

    log = postgres_session.scalar(
        select(NotificationLog).where(NotificationLog.transaction_id == expense.id)
    )
    assert log is not None
    assert log.status.value == "sent"
    assert log.attempt_count == 1

    second = create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            amount="5.00",
            transaction_date="2026-09-16",
            description="Outra despesa",
        ),
        postgres_session,
    )
    assert scan_new_expenses(postgres_session) == 1
    assert dispatch_notifications(
        postgres_session,
        FailingTelegramGateway(),
        chat_id="123456",
        max_attempts=1,
    ) == (0, 1)
    failed = postgres_session.scalar(
        select(NotificationLog).where(NotificationLog.transaction_id == second.id)
    )
    assert failed is not None
    assert failed.status.value == "failed"
    assert failed.attempt_count == 1
    assert failed.next_attempt_at is None
    assert failed.error_code == "telegram_unavailable"


@pytest.mark.migration
def test_telegram_commands_reject_other_chats_and_persist_offset(
    postgres_session: Session,
) -> None:
    gateway = FakeTelegramGateway(
        updates=[
            TelegramUpdate(update_id=20, chat_id="999999", text="/saldo"),
            TelegramUpdate(update_id=21, chat_id="123456", text="/saldo"),
        ]
    )

    assert process_telegram_updates(
        postgres_session,
        gateway,
        allowed_chat_id="123456",
        timeout=0,
    ) == (1, 1)
    assert len(gateway.sent) == 1
    assert gateway.sent[0][0] == "123456"
    assert "Saldo atual consolidado" in gateway.sent[0][1]

    assert process_telegram_updates(
        postgres_session,
        gateway,
        allowed_chat_id="123456",
        timeout=0,
    ) == (0, 0)
    assert gateway.offsets == [None, 22]
    checkpoint = postgres_session.scalar(
        select(IntegrationCheckpoint).where(
            IntegrationCheckpoint.integration == "telegram",
            IntegrationCheckpoint.stream == "bot_updates",
        )
    )
    assert checkpoint is not None
    assert checkpoint.cursor == {"update_id": 21}


@pytest.mark.migration
def test_dashboard_uses_snapshots_planning_and_reserve(postgres_session: Session) -> None:
    today = local_today("America/Campo_Grande")
    account = Account(
        name="Conta do painel",
        institution_name="INTER",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=Decimal("0.00"),
        is_active=True,
    )
    postgres_session.add(account)
    postgres_session.flush()
    postgres_session.add(
        BalanceSnapshot(
            account_id=account.id,
            amount=Decimal("1000.00"),
            currency_code="BRL",
            source=BalanceSnapshotSource.MANUAL,
            observed_at=datetime.now(UTC) - timedelta(days=1),
            external_id="dashboard-test",
        )
    )
    postgres_session.add(
        Transaction(
            account_id=account.id,
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.DEBIT,
            status=TransactionStatus.POSTED,
            amount=Decimal("100.00"),
            transaction_date=today,
            description_raw="Despesa de teste",
            description_normalized="despesa de teste",
            source=TransactionSource.MANUAL,
            classification_method="manual",
            is_reviewed=False,
            deduplication_hash="d" * 64,
        )
    )
    postgres_session.flush()
    update_budget_settings(BudgetSettingsUpdate(minimum_reserve="100.00"), postgres_session)
    create_expected_income(
        ExpectedIncomeCreate(
            name="Entrada de teste",
            expected_amount="500.00",
            expected_date=today + timedelta(days=1),
        ),
        postgres_session,
    )
    create_planned_expense(
        PlannedExpenseCreate(
            name="Conta de teste",
            expected_amount="200.00",
            due_date=today,
        ),
        postgres_session,
    )

    dashboard = get_dashboard(postgres_session)

    assert dashboard.current_balance == Decimal("900.00")
    assert dashboard.available_until_next_income == Decimal("600.00")
    assert dashboard.daily_safe_limit == Decimal("600.00")
    assert dashboard.committed_expenses == Decimal("200.00")
    assert dashboard.review_count == 1
