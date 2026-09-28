from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExpectedIncomeStatus, PlannedExpenseStatus, Recurrence
from app.models.types import enum_type


class ExpectedIncome(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "expected_incomes"
    __table_args__ = (
        CheckConstraint("expected_amount > 0", name="expected_amount_positive"),
        CheckConstraint(
            "actual_amount IS NULL OR actual_amount > 0", name="actual_amount_positive"
        ),
        CheckConstraint(
            "(status = 'received' AND matched_transaction_id IS NOT NULL "
            "AND actual_amount IS NOT NULL AND actual_date IS NOT NULL) OR "
            "(status <> 'received')",
            name="received_has_actual_values",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    expected_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recurrence: Mapped[Recurrence] = mapped_column(
        enum_type(Recurrence, "income_recurrence"), nullable=False
    )
    amount_is_variable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[ExpectedIncomeStatus] = mapped_column(
        enum_type(ExpectedIncomeStatus, "expected_income_status"), nullable=False
    )
    matched_transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), unique=True
    )
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    actual_date: Mapped[date | None] = mapped_column(Date)


class PlannedExpense(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "planned_expenses"
    __table_args__ = (
        CheckConstraint("expected_amount > 0", name="expected_amount_positive"),
        CheckConstraint(
            "(status = 'paid' AND matched_transaction_id IS NOT NULL) OR (status <> 'paid')",
            name="paid_has_transaction",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recurrence: Mapped[Recurrence] = mapped_column(
        enum_type(Recurrence, "expense_recurrence"), nullable=False
    )
    amount_is_variable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[PlannedExpenseStatus] = mapped_column(
        enum_type(PlannedExpenseStatus, "planned_expense_status"), nullable=False
    )
    matched_transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), unique=True
    )
