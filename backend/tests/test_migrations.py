import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, make_url, text
from sqlalchemy.exc import IntegrityError

from alembic import command

EXPECTED_TABLES = {
    "accounts",
    "alembic_version",
    "assistant_invocations",
    "audit_events",
    "balance_snapshots",
    "budget_settings",
    "categories",
    "category_suggestions",
    "category_rules",
    "expected_incomes",
    "import_files",
    "import_profiles",
    "import_rows",
    "integration_checkpoints",
    "notification_logs",
    "planned_expenses",
    "pluggy_account_links",
    "pluggy_items",
    "pluggy_transaction_links",
    "sync_runs",
    "service_tokens",
    "transactions",
    "transfer_groups",
}
BACKEND_DIR = Path(__file__).resolve().parents[1]


def require_test_database_url() -> str:
    database_url = os.environ.get("FINANCE_DATABASE_URL")
    if not database_url:
        pytest.skip("FINANCE_DATABASE_URL is required for migration tests")
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("migration tests refuse to modify a database without an _test suffix")
    return database_url


def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.mark.migration
def test_migrations_upgrade_downgrade_and_protect_money_invariants() -> None:
    database_url = require_test_database_url()
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM categories")).scalar_one() == 16
        assert (
            connection.execute(
                text("SELECT count(*) FROM import_profiles WHERE institution_name = 'INTER'")
            ).scalar_one()
            == 1
        )

    with engine.begin() as connection:
        account_id = connection.execute(
            text(
                "INSERT INTO accounts (name, type, initial_balance) "
                "VALUES ('Local test', 'checking', 0) RETURNING id"
            )
        ).scalar_one()

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO transactions "
                "(account_id, type, direction, status, amount, transaction_date, "
                "description_raw, description_normalized, source, "
                "classification_method, deduplication_hash) "
                "VALUES (:account_id, 'expense', 'debit', 'posted', -1, CURRENT_DATE, "
                "'invalid', 'invalid', 'manual', 'manual', repeat('0', 64))"
            ),
            {"account_id": account_id},
        )

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    engine.dispose()
