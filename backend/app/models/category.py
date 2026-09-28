from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CategoryKind, RuleMatchField, RuleOrigin
from app.models.types import enum_type


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    color: Mapped[str | None] = mapped_column(String(20))
    icon: Mapped[str | None] = mapped_column(String(80))
    kind: Mapped[CategoryKind] = mapped_column(
        enum_type(CategoryKind, "category_kind"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CategoryRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "category_rules"

    match_field: Mapped[RuleMatchField] = mapped_column(
        enum_type(RuleMatchField, "rule_match_field"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    origin: Mapped[RuleOrigin] = mapped_column(enum_type(RuleOrigin, "rule_origin"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
