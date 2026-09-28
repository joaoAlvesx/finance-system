"""Add scoped service tokens and assistant review records.

Revision ID: 0005_assistant_integration
Revises: 0004_pluggy_sync
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_assistant_integration"
down_revision: str | None = "0004_pluggy_sync"
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


def upgrade() -> None:
    op.create_table(
        "service_tokens",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_service_tokens"),
        sa.UniqueConstraint("name", name="uq_service_tokens_name"),
        sa.UniqueConstraint("token_hash", name="uq_service_tokens_token_hash"),
        sa.UniqueConstraint("token_prefix", name="uq_service_tokens_token_prefix"),
    )
    op.create_index("ix_service_tokens_token_prefix", "service_tokens", ["token_prefix"])

    op.create_table(
        "assistant_invocations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("service_token_id", sa.Uuid()),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("correlation_id", sa.String(120)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["service_token_id"], ["service_tokens.id"],
            name="fk_assistant_invocations_service_token_id_service_tokens",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_invocations"),
    )
    op.create_index(
        "ix_assistant_invocations_service_token_id", "assistant_invocations", ["service_token_id"]
    )
    op.create_index("ix_assistant_invocations_tool_name", "assistant_invocations", ["tool_name"])
    op.create_index(
        "ix_assistant_invocations_correlation_id", "assistant_invocations", ["correlation_id"]
    )

    op.create_table(
        "category_suggestions",
        *_identity_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_category_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("rationale_code", sa.String(80), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "accepted", "rejected",
                name="category_suggestion_status", native_enum=False, create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("suggested_by", sa.String(80), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["transactions.id"],
            name="fk_category_suggestions_transaction_id_transactions", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_category_id"], ["categories.id"],
            name="fk_category_suggestions_suggested_category_id_categories", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_category_suggestions"),
    )
    op.create_index(
        "ix_category_suggestions_transaction_id", "category_suggestions", ["transaction_id"]
    )
    op.create_index(
        "ix_category_suggestions_suggested_category_id",
        "category_suggestions", ["suggested_category_id"],
    )
    op.create_index(
        "uq_category_suggestions_pending_transaction",
        "category_suggestions", ["transaction_id"], unique=True,
        postgresql_where=sa.text("status = 'pending' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_category_suggestions_pending_transaction", table_name="category_suggestions"
    )
    op.drop_index(
        "ix_category_suggestions_suggested_category_id", table_name="category_suggestions"
    )
    op.drop_index("ix_category_suggestions_transaction_id", table_name="category_suggestions")
    op.drop_table("category_suggestions")
    op.drop_index("ix_assistant_invocations_correlation_id", table_name="assistant_invocations")
    op.drop_index("ix_assistant_invocations_tool_name", table_name="assistant_invocations")
    op.drop_index(
        "ix_assistant_invocations_service_token_id", table_name="assistant_invocations"
    )
    op.drop_table("assistant_invocations")
    op.drop_index("ix_service_tokens_token_prefix", table_name="service_tokens")
    op.drop_table("service_tokens")
