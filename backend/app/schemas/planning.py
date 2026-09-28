from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ExpectedIncomeStatus,
    PlannedExpenseStatus,
    Recurrence,
    SafeSpendingMode,
)
from app.schemas.common import Money, PositiveMoney


class ExpectedIncomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expected_amount: PositiveMoney
    expected_date: date
    recurrence: Recurrence = Recurrence.NONE
    amount_is_variable: bool = False


class ExpectedIncomePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    expected_amount: PositiveMoney | None = None
    expected_date: date | None = None
    recurrence: Recurrence | None = None
    amount_is_variable: bool | None = None
    status: ExpectedIncomeStatus | None = None

    @model_validator(mode="after")
    def received_requires_reconciliation(self) -> "ExpectedIncomePatch":
        if self.status == ExpectedIncomeStatus.RECEIVED:
            raise ValueError("received income must be reconciled with a transaction")
        return self


class ExpectedIncomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    expected_amount: PositiveMoney
    expected_date: date
    recurrence: Recurrence
    amount_is_variable: bool
    status: ExpectedIncomeStatus
    matched_transaction_id: UUID | None
    actual_amount: PositiveMoney | None
    actual_date: date | None
    created_at: datetime
    updated_at: datetime


class PlannedExpenseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expected_amount: PositiveMoney
    due_date: date
    recurrence: Recurrence = Recurrence.NONE
    amount_is_variable: bool = False
    category_id: UUID | None = None


class PlannedExpensePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    expected_amount: PositiveMoney | None = None
    due_date: date | None = None
    recurrence: Recurrence | None = None
    amount_is_variable: bool | None = None
    category_id: UUID | None = None
    status: PlannedExpenseStatus | None = None

    @model_validator(mode="after")
    def paid_requires_reconciliation(self) -> "PlannedExpensePatch":
        if self.status == PlannedExpenseStatus.PAID:
            raise ValueError("paid expense must be reconciled with a transaction")
        return self


class PlannedExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    expected_amount: PositiveMoney
    due_date: date
    recurrence: Recurrence
    amount_is_variable: bool
    category_id: UUID | None
    status: PlannedExpenseStatus
    matched_transaction_id: UUID | None
    created_at: datetime
    updated_at: datetime


class BudgetSettingsUpdate(BaseModel):
    minimum_reserve: Money
    include_pending_transactions: bool = True
    telegram_notifications_enabled: bool | None = None

    @model_validator(mode="after")
    def reserve_is_non_negative(self) -> "BudgetSettingsUpdate":
        if self.minimum_reserve < 0:
            raise ValueError("minimum reserve cannot be negative")
        return self


class BudgetSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    minimum_reserve: Money
    currency_code: str
    safe_spending_mode: SafeSpendingMode
    include_pending_transactions: bool
    telegram_notifications_enabled: bool
    timezone: str
    created_at: datetime
    updated_at: datetime
