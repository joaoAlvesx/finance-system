from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    CategorySuggestionStatus,
    TransactionDirection,
    TransactionStatus,
    TransactionType,
)
from app.schemas.common import Money, PositiveMoney


class BalanceResult(BaseModel):
    calculated_at: datetime
    account_id: UUID | None
    balance: Money
    currency_code: str = "BRL"
    value_kind: Literal["calculated"] = "calculated"


class AvailabilityResult(BaseModel):
    calculated_at: datetime
    current_balance: Money
    available_until_next_income: Money | None
    daily_safe_limit: Money | None
    committed_expenses: Money
    minimum_reserve: Money
    deficit: Money
    next_income_date: date | None
    days_until_next_income: int | None
    currency_code: str = "BRL"
    value_kind: Literal["calculated"] = "calculated"


class AssistantTransaction(BaseModel):
    id: UUID
    account_id: UUID
    transaction_date: date
    description: str
    amount: PositiveMoney
    direction: TransactionDirection
    type: TransactionType
    status: TransactionStatus
    category_id: UUID | None
    category_name: str | None


class TransactionListResult(BaseModel):
    items: list[AssistantTransaction]
    count: int
    limited: bool


class FutureExpenseResult(BaseModel):
    id: UUID
    name: str
    expected_amount: PositiveMoney
    due_date: date
    category_id: UUID | None
    status: str


class FutureExpenseListResult(BaseModel):
    items: list[FutureExpenseResult]
    count: int
    limited: bool


class MonthlyCategoryTotal(BaseModel):
    category_id: UUID | None
    category_name: str
    amount: Money


class MonthlySummaryResult(BaseModel):
    year: int
    month: int
    income: Money
    expense: Money
    net: Money
    by_category: list[MonthlyCategoryTotal]
    value_kind: Literal["calculated"] = "calculated"


class PurchaseSimulationRequest(BaseModel):
    amount: PositiveMoney


class PurchaseSimulationResult(BaseModel):
    amount: PositiveMoney
    balance_after_purchase: Money
    available_after_purchase: Money | None
    daily_safe_limit_after_purchase: Money | None
    deficit_after_purchase: Money
    next_income_date: date | None
    value_kind: Literal["prediction"] = "prediction"


class ManualTransactionRequest(BaseModel):
    account_id: UUID
    type: TransactionType
    direction: TransactionDirection
    amount: PositiveMoney
    transaction_date: date
    description: str = Field(min_length=1, max_length=1000)
    category_id: UUID | None = None
    confirmed: bool = False

    @model_validator(mode="after")
    def validate_direction(self) -> "ManualTransactionRequest":
        valid = (
            self.type == TransactionType.INCOME and self.direction == TransactionDirection.CREDIT
        ) or (self.type == TransactionType.EXPENSE and self.direction == TransactionDirection.DEBIT)
        if not valid:
            raise ValueError("type and direction do not match")
        return self


class CategoryChangeRequest(BaseModel):
    category_id: UUID
    confirmed: bool = False


class CategorySuggestionCreate(BaseModel):
    transaction_id: UUID
    category_id: UUID
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    rationale_code: str = Field(pattern=r"^[a-z0-9_]{1,80}$")


class CategorySuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    transaction_description: str
    transaction_amount: PositiveMoney
    suggested_category_id: UUID
    suggested_category_name: str
    confidence: Decimal
    rationale_code: str
    status: CategorySuggestionStatus
    suggested_by: str
    created_at: datetime


class CategorySuggestionDecision(BaseModel):
    decision: Literal["accept", "reject"]


class NaturalLanguageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class NaturalLanguageResponse(BaseModel):
    intent: str
    value_kind: Literal["calculated", "prediction", "suggestion"]
    answer: str
    data: dict[str, object] = Field(default_factory=dict)


class InsightCard(BaseModel):
    key: str
    title: str
    text: str
    value_kind: Literal["calculated", "prediction", "suggestion"]
    severity: Literal["neutral", "attention"] = "neutral"


class InsightsResponse(BaseModel):
    generated_at: datetime
    cards: list[InsightCard]
    suggested_questions: list[str]
