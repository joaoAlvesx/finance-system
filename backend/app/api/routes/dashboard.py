from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import DatabaseSession
from app.models.transaction import Transaction
from app.schemas.dashboard import (
    DashboardCategoryTotal,
    DashboardNextIncome,
    DashboardResponse,
)
from app.schemas.transactions import TransactionRead
from app.services.dashboard import (
    availability_values,
    category_spending,
    consolidated_current_balance,
    default_budget_settings,
    local_today,
    month_totals,
    next_expected_income,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(session: DatabaseSession) -> DashboardResponse:
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    balance = consolidated_current_balance(session, timezone=settings.timezone)
    income = next_expected_income(session, today=today)
    available, daily, committed, deficit = availability_values(
        session,
        balance=balance,
        reserve=settings.minimum_reserve,
        today=today,
        income=income,
    )
    month_income, month_expense = month_totals(session, today=today)
    review_count = session.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.deleted_at.is_(None), Transaction.is_reviewed.is_(False)
        )
    )
    uncategorized_count = session.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.deleted_at.is_(None), Transaction.category_id.is_(None)
        )
    )
    recent = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.deleted_at.is_(None))
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .limit(6)
        )
    )
    categories = category_spending(session, today=today)
    session.commit()
    return DashboardResponse(
        generated_at=datetime.now(UTC),
        current_balance=balance,
        available_until_next_income=available,
        daily_safe_limit=daily,
        committed_expenses=committed,
        deficit=deficit,
        minimum_reserve=settings.minimum_reserve,
        month_income=month_income,
        month_expense=month_expense,
        review_count=review_count or 0,
        uncategorized_count=uncategorized_count or 0,
        next_income=(
            DashboardNextIncome(
                id=income.id,
                name=income.name,
                expected_amount=income.expected_amount,
                expected_date=income.expected_date,
            )
            if income
            else None
        ),
        spending_by_category=[
            DashboardCategoryTotal(
                category_id=category_id,
                category_name=name,
                amount=amount,
            )
            for category_id, name, amount in categories
        ],
        recent_transactions=[TransactionRead.model_validate(item) for item in recent],
    )
