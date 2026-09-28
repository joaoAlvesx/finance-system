"""Create the financial foundation schema.

Revision ID: 0001_foundation
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "accounts",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("institution_name", sa.String(120)),
        sa.Column(
            "type",
            _enum("account_type", "checking", "savings", "cash", "other"),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(3), server_default="BRL", nullable=False),
        sa.Column("initial_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("pluggy_account_id", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("pluggy_account_id", name="uq_accounts_pluggy_account_id"),
    )

    op.create_table(
        "transfer_groups",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(500)),
        sa.PrimaryKeyConstraint("id", name="pk_transfer_groups"),
    )

    op.create_table(
        "categories",
        *_identity_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("color", sa.String(20)),
        sa.Column("icon", sa.String(80)),
        sa.Column(
            "kind",
            _enum("category_kind", "expense", "income", "both"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name="fk_categories_parent_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "budget_settings",
        *_identity_columns(),
        sa.Column("minimum_reserve", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="BRL", nullable=False),
        sa.Column(
            "safe_spending_mode",
            _enum("safe_spending_mode", "until_next_income"),
            server_default="until_next_income",
            nullable=False,
        ),
        sa.Column(
            "include_pending_transactions", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "notification_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("timezone", sa.String(80), server_default="America/Campo_Grande", nullable=False),
        sa.Column(
            "telegram_notifications_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.CheckConstraint("minimum_reserve >= 0", name="minimum_reserve_non_negative"),
        sa.CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
        sa.PrimaryKeyConstraint("id", name="pk_budget_settings"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column(
            "changed_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "actor_type",
            _enum("audit_actor_type", "user", "service", "system"),
            nullable=False,
        ),
        sa.Column("actor_identifier", sa.String(120)),
        sa.Column("correlation_id", sa.String(120)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_aggregate_id", "audit_events", ["aggregate_id"])
    op.create_index("ix_audit_events_aggregate_type", "audit_events", ["aggregate_type"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="BRL", nullable=False),
        sa.Column(
            "source",
            _enum(
                "balance_snapshot_source", "initial", "manual", "csv", "pluggy", "reconciliation"
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_balance_snapshots_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_balance_snapshots"),
        sa.UniqueConstraint(
            "account_id", "source", "external_id", name="uq_balance_snapshot_external_origin"
        ),
    )
    op.create_index("ix_balance_snapshots_account_id", "balance_snapshots", ["account_id"])
    op.create_index("ix_balance_snapshots_observed_at", "balance_snapshots", ["observed_at"])

    op.create_table(
        "category_rules",
        *_identity_columns(),
        sa.Column(
            "match_field",
            _enum("rule_match_field", "description", "merchant", "external_id"),
            nullable=False,
        ),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("account_id", sa.Uuid()),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "origin",
            _enum("rule_origin", "manual", "confirmed_correction"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_category_rules_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_category_rules_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_category_rules"),
    )
    op.create_index("ix_category_rules_account_id", "category_rules", ["account_id"])
    op.create_index("ix_category_rules_category_id", "category_rules", ["category_id"])

    op.create_table(
        "transactions",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            _enum("transaction_type", "income", "expense", "transfer"),
            nullable=False,
        ),
        sa.Column(
            "direction",
            _enum("transaction_direction", "credit", "debit"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("transaction_status", "pending", "posted", "ignored"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("description_raw", sa.String(1000), nullable=False),
        sa.Column("description_normalized", sa.String(1000), nullable=False),
        sa.Column("merchant_name", sa.String(255)),
        sa.Column("category_id", sa.Uuid()),
        sa.Column(
            "source",
            _enum("transaction_source", "manual", "csv", "pluggy", "telegram"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255)),
        sa.Column("source_file_id", sa.Uuid()),
        sa.Column("classification_confidence", sa.Numeric(5, 4)),
        sa.Column(
            "classification_method",
            _enum("classification_method", "manual", "rule", "history", "ai", "pluggy"),
            nullable=False,
        ),
        sa.Column("is_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.String(2000)),
        sa.Column("deduplication_hash", sa.String(64), nullable=False),
        sa.Column("transfer_group_id", sa.Uuid()),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint(
            "classification_confidence IS NULL OR "
            "(classification_confidence >= 0 AND classification_confidence <= 1)",
            name="classification_confidence_range",
        ),
        sa.CheckConstraint(
            "(type = 'transfer' AND transfer_group_id IS NOT NULL) OR "
            "(type <> 'transfer' AND transfer_group_id IS NULL)",
            name="transfer_has_group",
        ),
        sa.CheckConstraint(
            "(type = 'income' AND direction = 'credit') OR "
            "(type = 'expense' AND direction = 'debit') OR "
            "(type = 'transfer' AND direction IN ('credit', 'debit'))",
            name="type_matches_direction",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_transactions_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_transactions_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_group_id"],
            ["transfer_groups.id"],
            name="fk_transactions_transfer_group_id_transfer_groups",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transactions"),
        sa.UniqueConstraint(
            "account_id", "source", "external_id", name="uq_transaction_external_origin"
        ),
    )
    op.create_index(
        "ix_transactions_account_date", "transactions", ["account_id", "transaction_date"]
    )
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.create_index("ix_transactions_deduplication_hash", "transactions", ["deduplication_hash"])
    op.create_index("ix_transactions_transfer_group_id", "transactions", ["transfer_group_id"])

    op.create_table(
        "expected_incomes",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=False),
        sa.Column("recurrence", _enum("income_recurrence", "none", "monthly"), nullable=False),
        sa.Column("amount_is_variable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "status",
            _enum("expected_income_status", "expected", "received", "late", "cancelled"),
            nullable=False,
        ),
        sa.Column("matched_transaction_id", sa.Uuid()),
        sa.Column("actual_amount", sa.Numeric(14, 2)),
        sa.Column("actual_date", sa.Date()),
        sa.CheckConstraint(
            "actual_amount IS NULL OR actual_amount > 0",
            name="actual_amount_positive",
        ),
        sa.CheckConstraint("expected_amount > 0", name="expected_amount_positive"),
        sa.CheckConstraint(
            "(status = 'received' AND matched_transaction_id IS NOT NULL "
            "AND actual_amount IS NOT NULL AND actual_date IS NOT NULL) OR "
            "(status <> 'received')",
            name="received_has_actual_values",
        ),
        sa.ForeignKeyConstraint(
            ["matched_transaction_id"],
            ["transactions.id"],
            name="fk_expected_incomes_matched_transaction_id_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_expected_incomes"),
        sa.UniqueConstraint(
            "matched_transaction_id", name="uq_expected_incomes_matched_transaction_id"
        ),
    )
    op.create_index("ix_expected_incomes_expected_date", "expected_incomes", ["expected_date"])

    op.create_table(
        "planned_expenses",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("recurrence", _enum("expense_recurrence", "none", "monthly"), nullable=False),
        sa.Column("amount_is_variable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("category_id", sa.Uuid()),
        sa.Column(
            "status",
            _enum("planned_expense_status", "planned", "paid", "late", "cancelled"),
            nullable=False,
        ),
        sa.Column("matched_transaction_id", sa.Uuid()),
        sa.CheckConstraint("expected_amount > 0", name="expected_amount_positive"),
        sa.CheckConstraint(
            "(status = 'paid' AND matched_transaction_id IS NOT NULL) OR (status <> 'paid')",
            name="paid_has_transaction",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_planned_expenses_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["matched_transaction_id"],
            ["transactions.id"],
            name="fk_planned_expenses_matched_transaction_id_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_planned_expenses"),
        sa.UniqueConstraint(
            "matched_transaction_id", name="uq_planned_expenses_matched_transaction_id"
        ),
    )
    op.create_index("ix_planned_expenses_category_id", "planned_expenses", ["category_id"])
    op.create_index("ix_planned_expenses_due_date", "planned_expenses", ["due_date"])


def downgrade() -> None:
    op.drop_table("planned_expenses")
    op.drop_table("expected_incomes")
    op.drop_table("transactions")
    op.drop_table("category_rules")
    op.drop_table("balance_snapshots")
    op.drop_table("audit_events")
    op.drop_table("budget_settings")
    op.drop_table("categories")
    op.drop_table("transfer_groups")
    op.drop_table("accounts")
