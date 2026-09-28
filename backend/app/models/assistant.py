from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import CategorySuggestionStatus
from app.models.types import enum_type


class ServiceToken(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Hashed credential used by an isolated internal service."""

    __tablename__ = "service_tokens"
    __table_args__ = (
        UniqueConstraint("token_prefix", name="uq_service_tokens_token_prefix"),
    )

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AssistantInvocation(UUIDPrimaryKeyMixin, Base):
    """Payload-free audit record for assistant tool calls."""

    __tablename__ = "assistant_invocations"

    service_token_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("service_tokens.id", ondelete="RESTRICT"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    correlation_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class CategorySuggestion(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Reviewable category proposal; accepting it is a separate audited action."""

    __tablename__ = "category_suggestions"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="confidence_range"
        ),
        Index(
            "uq_category_suggestions_pending_transaction",
            "transaction_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND deleted_at IS NULL"),
        ),
    )

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    suggested_category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    rationale_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[CategorySuggestionStatus] = mapped_column(
        enum_type(CategorySuggestionStatus, "category_suggestion_status"), nullable=False
    )
    suggested_by: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
