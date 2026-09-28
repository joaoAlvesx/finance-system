"""Add Telegram notification outbox and integration checkpoints.

Revision ID: 0003_telegram_notifications
Revises: 0002_csv_imports
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_telegram_notifications"
down_revision: str | None = "0002_csv_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "integration_checkpoints",
        *_identity_columns(),
        sa.Column("integration", sa.String(50), nullable=False),
        sa.Column("stream", sa.String(80), nullable=False),
        sa.Column(
            "cursor",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_integration_checkpoints"),
        sa.UniqueConstraint("integration", "stream", name="uq_integration_checkpoint_stream"),
    )

    op.create_table(
        "notification_logs",
        *_identity_columns(),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("notification_type", sa.String(80), nullable=False),
        sa.Column("transaction_id", sa.Uuid()),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="notification_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("external_message_id", sa.String(120)),
        sa.Column("error_code", sa.String(120)),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_notification_logs_transaction_id_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_logs"),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_logs_idempotency_key"),
    )
    op.create_index("ix_notification_logs_transaction_id", "notification_logs", ["transaction_id"])
    op.create_index(
        "ix_notification_logs_next_attempt_at", "notification_logs", ["next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notification_logs_next_attempt_at", table_name="notification_logs")
    op.drop_index("ix_notification_logs_transaction_id", table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_table("integration_checkpoints")
