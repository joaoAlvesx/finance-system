from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import AuditActorType
from app.models.types import enum_type


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only metadata about changes; financial payloads do not belong here."""

    __tablename__ = "audit_events"

    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    change_data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    actor_type: Mapped[AuditActorType] = mapped_column(
        enum_type(AuditActorType, "audit_actor_type"), nullable=False
    )
    actor_identifier: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
