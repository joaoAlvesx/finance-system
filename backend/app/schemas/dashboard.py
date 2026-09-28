from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import Money, PositiveMoney
from app.schemas.transactions import TransactionRead


class DashboardCategoryTotal(BaseModel):
    category_id: UUID | None
    category_name: str
    amount: Money


class DashboardNextIncome(BaseModel):
    id: UUID
    name: str
    expected_amount: PositiveMoney
    expected_date: date


class DashboardResponse(BaseModel):
    generated_at: datetime
    current_balance: Money
    available_until_next_income: Money | None
    daily_safe_limit: Money | None
    committed_expenses: Money
    deficit: Money
    minimum_reserve: Money
    month_income: Money
    month_expense: Money
    review_count: int
    uncategorized_count: int
    next_income: DashboardNextIncome | None
    spending_by_category: list[DashboardCategoryTotal]
    recent_transactions: list[TransactionRead]
