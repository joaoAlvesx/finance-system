from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NotificationStatus, SyncRunStatus, SyncTrigger
from app.models.types import enum_type


class IntegrationCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_checkpoints"
    __table_args__ = (
        UniqueConstraint("integration", "stream", name="uq_integration_checkpoint_stream"),
    )

    integration: Mapped[str] = mapped_column(String(50), nullable=False)
    stream: Mapped[str] = mapped_column(String(80), nullable=False)
    cursor: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_logs_idempotency_key"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[NotificationStatus] = mapped_column(
        enum_type(NotificationStatus, "notification_status"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_message_id: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(120))


class PluggyItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pluggy_items"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_non_negative"),
    )

    external_item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    connector_id: Mapped[int | None] = mapped_column(Integer)
    connector_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="UPDATING", nullable=False)
    execution_status: Mapped[str | None] = mapped_column(String(60))
    error_code: Mapped[str | None] = mapped_column(String(120))
    requires_user_action: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PluggyAccountLink(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pluggy_account_links"
    __table_args__ = (
        UniqueConstraint("external_account_id", name="uq_pluggy_account_links_external_id"),
        UniqueConstraint("local_account_id", name="uq_pluggy_account_links_local_account"),
        CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
    )

    pluggy_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("pluggy_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    local_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    external_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(60))
    currency_code: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint("accounts_consulted >= 0", name="accounts_consulted_non_negative"),
        CheckConstraint("created_count >= 0", name="created_count_non_negative"),
        CheckConstraint("updated_count >= 0", name="updated_count_non_negative"),
        CheckConstraint("reconciled_count >= 0", name="reconciled_count_non_negative"),
        CheckConstraint("ignored_count >= 0", name="ignored_count_non_negative"),
    )

    integration: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    pluggy_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pluggy_items.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[SyncRunStatus] = mapped_column(
        enum_type(SyncRunStatus, "sync_run_status"), nullable=False, index=True
    )
    trigger: Mapped[SyncTrigger] = mapped_column(
        enum_type(SyncTrigger, "sync_trigger"), nullable=False
    )
    full_reconciliation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accounts_consulted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reconciled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cursor: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))


class PluggyTransactionLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pluggy_transaction_links"
    __table_args__ = (
        UniqueConstraint(
            "pluggy_account_link_id",
            "external_transaction_id",
            name="uq_pluggy_transaction_links_external_id",
        ),
    )

    pluggy_account_link_id: Mapped[UUID] = mapped_column(
        ForeignKey("pluggy_account_links.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_transaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_managed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
