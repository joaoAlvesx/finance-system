from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ClassificationMethod,
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.types import enum_type


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(type = 'income' AND direction = 'credit') OR "
            "(type = 'expense' AND direction = 'debit') OR "
            "(type = 'transfer' AND direction IN ('credit', 'debit'))",
            name="type_matches_direction",
        ),
        CheckConstraint(
            "(type = 'transfer' AND transfer_group_id IS NOT NULL) OR "
            "(type <> 'transfer' AND transfer_group_id IS NULL)",
            name="transfer_has_group",
        ),
        CheckConstraint(
            "classification_confidence IS NULL OR "
            "(classification_confidence >= 0 AND classification_confidence <= 1)",
            name="classification_confidence_range",
        ),
        UniqueConstraint(
            "account_id", "source", "external_id", name="uq_transaction_external_origin"
        ),
        Index("ix_transactions_deduplication_hash", "deduplication_hash"),
        Index("ix_transactions_account_date", "account_id", "transaction_date"),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[TransactionType] = mapped_column(
        enum_type(TransactionType, "transaction_type"), nullable=False
    )
    direction: Mapped[TransactionDirection] = mapped_column(
        enum_type(TransactionDirection, "transaction_direction"), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        enum_type(TransactionStatus, "transaction_status"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description_raw: Mapped[str] = mapped_column(String(1000), nullable=False)
    description_normalized: Mapped[str] = mapped_column(String(1000), nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[TransactionSource] = mapped_column(
        enum_type(TransactionSource, "transaction_source"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    source_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_files.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    classification_method: Mapped[ClassificationMethod] = mapped_column(
        enum_type(ClassificationMethod, "classification_method"), nullable=False
    )
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    deduplication_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    transfer_group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transfer_groups.id", ondelete="RESTRICT"), index=True
    )
