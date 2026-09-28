import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from alembic import command
from app.core.service_auth import (
    DEFAULT_HERMES_SCOPES,
    TOKEN_PREFIX_LENGTH,
    WRITE_SCOPE,
    token_digest,
)
from app.db.session import get_db_session
from app.main import app
from app.models.account import Account
from app.models.assistant import AssistantInvocation, ServiceToken
from app.models.audit import AuditEvent
from app.models.category import Category
from app.models.enums import AccountType, CategoryKind, ExpectedIncomeStatus, Recurrence
from app.models.planning import ExpectedIncome
from app.services.assistant import natural_language_answer
from app.services.dashboard import default_budget_settings, local_today

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


def seed_account_and_planning(session: Session) -> tuple[Account, Category]:
    account = Account(
        name="Conta assistente",
        type=AccountType.CHECKING,
        currency_code="BRL",
        initial_balance=Decimal("1000.00"),
        is_active=True,
    )
    category = Category(
        name="Categoria assistente",
        kind=CategoryKind.EXPENSE,
        color="#123456",
        icon="test",
        is_active=True,
    )
    session.add_all([account, category])
    session.flush()
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    session.add(
        ExpectedIncome(
            name="Próxima renda",
            expected_amount=Decimal("500.00"),
            expected_date=today + timedelta(days=10),
            recurrence=Recurrence.NONE,
            amount_is_variable=False,
            status=ExpectedIncomeStatus.EXPECTED,
        )
    )
    session.commit()
    return account, category


@pytest.mark.migration
def test_natural_language_calculations_are_deterministic(postgres_session: Session) -> None:
    seed_account_and_planning(postgres_session)
    balance = natural_language_answer(postgres_session, "Qual é meu saldo?")
    simulation = natural_language_answer(
        postgres_session, "Simule um gasto de R$ 100,00"
    )

    assert balance.value_kind == "calculated"
    assert balance.data["balance"] == "1000.00"
    assert simulation.value_kind == "prediction"
    assert simulation.data["balance_after_purchase"] == "900.00"


@pytest.mark.migration
@pytest.mark.anyio
async def test_service_scopes_confirmation_and_payload_free_audit(
    postgres_session: Session,
) -> None:
    account, category = seed_account_and_planning(postgres_session)
    read_token = "fst_read_only_test_token_123456789"
    write_token = "fst_write_test_token_123456789"
    postgres_session.add_all(
        [
            ServiceToken(
                name="hermes-read-test",
                token_prefix=read_token[:TOKEN_PREFIX_LENGTH],
                token_hash=token_digest(read_token),
                scopes=DEFAULT_HERMES_SCOPES,
                is_active=True,
            ),
            ServiceToken(
                name="hermes-write-test",
                token_prefix=write_token[:TOKEN_PREFIX_LENGTH],
                token_hash=token_digest(write_token),
                scopes=[*DEFAULT_HERMES_SCOPES, WRITE_SCOPE],
                is_active=True,
            ),
        ]
    )
    postgres_session.commit()

    def override_session():
        yield postgres_session

    app.dependency_overrides[get_db_session] = override_session
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            balance_response = await client.get(
                "/api/v1/assistant/tools/balance",
                headers={"Authorization": f"Bearer {read_token}"},
            )
            denied_response = await client.post(
                "/api/v1/assistant/tools/manual-transactions",
                headers={"Authorization": f"Bearer {read_token}"},
                json={
                    "account_id": str(account.id),
                    "type": "expense",
                    "direction": "debit",
                    "amount": "20.00",
                    "transaction_date": local_today("America/Campo_Grande").isoformat(),
                    "description": "Compra teste",
                    "category_id": str(category.id),
                    "confirmed": True,
                },
            )
            confirmation_response = await client.post(
                "/api/v1/assistant/tools/manual-transactions",
                headers={"Authorization": f"Bearer {write_token}"},
                json={
                    "account_id": str(account.id),
                    "type": "expense",
                    "direction": "debit",
                    "amount": "20.00",
                    "transaction_date": local_today("America/Campo_Grande").isoformat(),
                    "description": "Compra teste",
                    "category_id": str(category.id),
                    "confirmed": False,
                },
            )
            created_response = await client.post(
                "/api/v1/assistant/tools/manual-transactions",
                headers={"Authorization": f"Bearer {write_token}"},
                json={
                    "account_id": str(account.id),
                    "type": "expense",
                    "direction": "debit",
                    "amount": "20.00",
                    "transaction_date": local_today("America/Campo_Grande").isoformat(),
                    "description": "Compra teste",
                    "category_id": str(category.id),
                    "confirmed": True,
                },
            )
            suggestion_response = await client.post(
                "/api/v1/assistant/tools/category-suggestions",
                headers={"Authorization": f"Bearer {read_token}"},
                json={
                    "transaction_id": created_response.json()["id"],
                    "category_id": str(category.id),
                    "confidence": "0.9200",
                    "rationale_code": "merchant_history",
                },
            )
            decision_response = await client.post(
                f"/api/v1/assistant/suggestions/{suggestion_response.json()['id']}/decision",
                json={"decision": "accept"},
            )
    finally:
        app.dependency_overrides.clear()

    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "1000.00"
    assert denied_response.status_code == 403
    assert confirmation_response.status_code == 409
    assert created_response.status_code == 201
    assert suggestion_response.status_code == 201
    assert suggestion_response.json()["status"] == "pending"
    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "accepted"
    invocation = postgres_session.scalar(
        select(AssistantInvocation).where(
            AssistantInvocation.tool_name == "registrar_transacao_manual"
        )
    )
    assert invocation is not None
    assert not hasattr(invocation, "request_payload")
    audit = postgres_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "transaction_created_by_service")
    )
    assert audit is not None
    assert audit.actor_identifier == "hermes-write-test"
