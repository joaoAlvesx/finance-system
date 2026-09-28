from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import ImportRowStatus, ImportStatus, TransactionDirection
from app.models.types import enum_type


class ImportProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_profiles"
    __table_args__ = (
        UniqueConstraint("institution_name", "name", name="uq_import_profile_institution_name"),
    )

    institution_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    encoding: Mapped[str] = mapped_column(String(40), nullable=False)
    delimiter: Mapped[str] = mapped_column(String(1), nullable=False)
    date_format: Mapped[str] = mapped_column(String(40), nullable=False)
    decimal_separator: Mapped[str] = mapped_column(String(1), nullable=False)
    column_mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class ImportFile(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "import_files"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="file_size_positive"),
        CheckConstraint("total_rows >= 0", name="total_rows_non_negative"),
        CheckConstraint("valid_rows >= 0", name="valid_rows_non_negative"),
        CheckConstraint("duplicate_rows >= 0", name="duplicate_rows_non_negative"),
        CheckConstraint("invalid_rows >= 0", name="invalid_rows_non_negative"),
        UniqueConstraint("account_id", "sha256", name="uq_import_file_account_hash"),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_profiles.id", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    institution_name: Mapped[str] = mapped_column(String(120), nullable=False)
    encoding: Mapped[str] = mapped_column(String(40), nullable=False)
    delimiter: Mapped[str] = mapped_column(String(1), nullable=False)
    column_mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, "import_status"), nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actor_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        CheckConstraint("row_number > 0", name="row_number_positive"),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        UniqueConstraint("import_file_id", "row_number", name="uq_import_row_file_number"),
    )

    import_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_files.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    historical_label: Mapped[str | None] = mapped_column(String(255))
    description_raw: Mapped[str | None] = mapped_column(String(1000))
    description_normalized: Mapped[str | None] = mapped_column(String(1000))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    direction: Mapped[TransactionDirection | None] = mapped_column(
        enum_type(TransactionDirection, "import_row_direction")
    )
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    deduplication_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ImportRowStatus] = mapped_column(
        enum_type(ImportRowStatus, "import_row_status"), nullable=False
    )
    error_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    suggested_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
