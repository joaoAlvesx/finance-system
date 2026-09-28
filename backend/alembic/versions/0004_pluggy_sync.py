"""Add Pluggy connection, account mapping and synchronization records.

Revision ID: 0004_pluggy_sync
Revises: 0003_telegram_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_pluggy_sync"
down_revision: str | None = "0003_telegram_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "pluggy_items",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("external_item_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.Integer()),
        sa.Column("connector_name", sa.String(120)),
        sa.Column("status", sa.String(40), server_default="UPDATING", nullable=False),
        sa.Column("execution_status", sa.String(60)),
        sa.Column("error_code", sa.String(120)),
        sa.Column("requires_user_action", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("consent_expires_at", sa.DateTime(timezone=True)),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True)),
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_pluggy_items"),
        sa.UniqueConstraint("external_item_id", name="uq_pluggy_items_external_item_id"),
    )
    op.create_index("ix_pluggy_items_next_sync_at", "pluggy_items", ["next_sync_at"])

    op.create_table(
        "pluggy_account_links",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("pluggy_item_id", sa.Uuid(), nullable=False),
        sa.Column("local_account_id", sa.Uuid()),
        sa.Column("external_account_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("account_type", sa.String(30), nullable=False),
        sa.Column("subtype", sa.String(60)),
        sa.Column("currency_code", sa.String(3), server_default="BRL", nullable=False),
        sa.Column("balance", sa.Numeric(14, 2)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
        sa.ForeignKeyConstraint(
            ["pluggy_item_id"],
            ["pluggy_items.id"],
            name="fk_pluggy_account_links_pluggy_item_id_pluggy_items",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_account_id"],
            ["accounts.id"],
            name="fk_pluggy_account_links_local_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pluggy_account_links"),
        sa.UniqueConstraint("external_account_id", name="uq_pluggy_account_links_external_id"),
        sa.UniqueConstraint("local_account_id", name="uq_pluggy_account_links_local_account"),
    )
    op.create_index(
        "ix_pluggy_account_links_pluggy_item_id",
        "pluggy_account_links",
        ["pluggy_item_id"],
    )
    op.create_index(
        "ix_pluggy_account_links_local_account_id",
        "pluggy_account_links",
        ["local_account_id"],
    )

    op.create_table(
        "sync_runs",
        *_identity_columns(),
        sa.Column("integration", sa.String(50), nullable=False),
        sa.Column("pluggy_item_id", sa.Uuid()),
        sa.Column(
            "status",
            _enum("sync_run_status", "pending", "running", "success", "partial", "failed"),
            nullable=False,
        ),
        sa.Column(
            "trigger",
            _enum("sync_trigger", "connection", "manual", "scheduled"),
            nullable=False,
        ),
        sa.Column("full_reconciliation", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("accounts_consulted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reconciled_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ignored_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cursor",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(120)),
        sa.CheckConstraint("accounts_consulted >= 0", name="accounts_consulted_non_negative"),
        sa.CheckConstraint("created_count >= 0", name="created_count_non_negative"),
        sa.CheckConstraint("updated_count >= 0", name="updated_count_non_negative"),
        sa.CheckConstraint("reconciled_count >= 0", name="reconciled_count_non_negative"),
        sa.CheckConstraint("ignored_count >= 0", name="ignored_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["pluggy_item_id"],
            ["pluggy_items.id"],
            name="fk_sync_runs_pluggy_item_id_pluggy_items",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_runs"),
    )
    op.create_index("ix_sync_runs_integration", "sync_runs", ["integration"])
    op.create_index("ix_sync_runs_pluggy_item_id", "sync_runs", ["pluggy_item_id"])
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])

    op.create_table(
        "pluggy_transaction_links",
        *_identity_columns(),
        sa.Column("pluggy_account_link_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("external_transaction_id", sa.String(64), nullable=False),
        sa.Column("provider_managed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["pluggy_account_link_id"],
            ["pluggy_account_links.id"],
            name="fk_pluggy_tx_links_account_link",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_pluggy_transaction_links_transaction_id_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pluggy_transaction_links"),
        sa.UniqueConstraint(
            "pluggy_account_link_id",
            "external_transaction_id",
            name="uq_pluggy_transaction_links_external_id",
        ),
    )
    op.create_index(
        "ix_pluggy_transaction_links_pluggy_account_link_id",
        "pluggy_transaction_links",
        ["pluggy_account_link_id"],
    )
    op.create_index(
        "ix_pluggy_transaction_links_transaction_id",
        "pluggy_transaction_links",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pluggy_transaction_links_transaction_id", table_name="pluggy_transaction_links"
    )
    op.drop_index(
        "ix_pluggy_transaction_links_pluggy_account_link_id",
        table_name="pluggy_transaction_links",
    )
    op.drop_table("pluggy_transaction_links")
    op.drop_index("ix_sync_runs_status", table_name="sync_runs")
    op.drop_index("ix_sync_runs_pluggy_item_id", table_name="sync_runs")
    op.drop_index("ix_sync_runs_integration", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_pluggy_account_links_local_account_id", table_name="pluggy_account_links")
    op.drop_index("ix_pluggy_account_links_pluggy_item_id", table_name="pluggy_account_links")
    op.drop_table("pluggy_account_links")
    op.drop_index("ix_pluggy_items_next_sync_at", table_name="pluggy_items")
    op.drop_table("pluggy_items")
