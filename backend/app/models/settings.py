from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SafeSpendingMode
from app.models.types import enum_type


class BudgetSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budget_settings"
    __table_args__ = (
        CheckConstraint("minimum_reserve >= 0", name="minimum_reserve_non_negative"),
        CheckConstraint("char_length(currency_code) = 3", name="currency_code_length"),
    )

    minimum_reserve: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    safe_spending_mode: Mapped[SafeSpendingMode] = mapped_column(
        enum_type(SafeSpendingMode, "safe_spending_mode"), nullable=False
    )
    include_pending_transactions: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notification_thresholds: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    timezone: Mapped[str] = mapped_column(
        String(80), default="America/Campo_Grande", nullable=False
    )
    telegram_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
