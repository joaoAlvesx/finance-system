from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import AccountType, BalanceSnapshotSource
from app.models.types import enum_type


class Account(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(120))
    type: Mapped[AccountType] = mapped_column(
        enum_type(AccountType, "account_type"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    pluggy_account_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TransferGroup(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "transfer_groups"

    notes: Mapped[str | None] = mapped_column(String(500))


class BalanceSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
        UniqueConstraint(
            "account_id", "source", "external_id", name="uq_balance_snapshot_external_origin"
        ),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    source: Mapped[BalanceSnapshotSource] = mapped_column(
        enum_type(BalanceSnapshotSource, "balance_snapshot_source"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
