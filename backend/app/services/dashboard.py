from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot
from app.models.category import Category
from app.models.enums import (
    ExpectedIncomeStatus,
    PlannedExpenseStatus,
    SafeSpendingMode,
    TransactionDirection,
    TransactionStatus,
    TransactionType,
)
from app.models.planning import ExpectedIncome, PlannedExpense
from app.models.settings import BudgetSettings
from app.models.transaction import Transaction
from app.services.money import money
from app.services.projections import (
    CashFlowStatus,
    PlannedCashFlow,
    available_until_next_income,
    safe_daily_limit,
)


def account_balance_at_present(
    session: Session,
    account: Account,
    *,
    timezone: str,
) -> Decimal:
    snapshot = session.scalar(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account.id)
        .order_by(BalanceSnapshot.observed_at.desc(), BalanceSnapshot.created_at.desc())
        .limit(1)
    )
    if snapshot is None:
        balance = account.initial_balance
        after_date: date | None = None
    else:
        balance = snapshot.amount
        after_date = snapshot.observed_at.astimezone(ZoneInfo(timezone)).date()

    statement = select(Transaction.amount, Transaction.direction).where(
        Transaction.account_id == account.id,
        Transaction.deleted_at.is_(None),
        Transaction.status != TransactionStatus.IGNORED,
    )
    if after_date is not None:
        statement = statement.where(Transaction.transaction_date > after_date)
    for amount, direction in session.execute(statement):
        balance += amount if direction == TransactionDirection.CREDIT else -amount
    return money(balance)


def consolidated_current_balance(session: Session, *, timezone: str) -> Decimal:
    accounts = session.scalars(
        select(Account).where(Account.deleted_at.is_(None), Account.is_active.is_(True))
    )
    return money(
        sum(
            (
                account_balance_at_present(session, account, timezone=timezone)
                for account in accounts
            ),
            Decimal("0.00"),
        )
    )


def month_totals(session: Session, *, today: date) -> tuple[Decimal, Decimal]:
    month_start = today.replace(day=1)
    rows = session.execute(
        select(Transaction.amount, Transaction.direction).where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type != TransactionType.TRANSFER,
            Transaction.transaction_date >= month_start,
            Transaction.transaction_date <= today,
        )
    )
    income = Decimal("0.00")
    expense = Decimal("0.00")
    for amount, direction in rows:
        if direction == TransactionDirection.CREDIT:
            income += amount
        else:
            expense += amount
    return money(income), money(expense)


def category_spending(
    session: Session, *, today: date, limit: int = 6
) -> list[tuple[object | None, str, Decimal]]:
    month_start = today.replace(day=1)
    rows = session.execute(
        select(
            Transaction.category_id,
            func.coalesce(Category.name, "Sem categoria"),
            func.sum(Transaction.amount),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.transaction_date >= month_start,
            Transaction.transaction_date <= today,
        )
        .group_by(Transaction.category_id, Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )
    return [(category_id, name, money(amount)) for category_id, name, amount in rows]


def default_budget_settings(session: Session) -> BudgetSettings:
    settings = session.scalar(select(BudgetSettings).order_by(BudgetSettings.created_at).limit(1))
    if settings is not None:
        return settings
    settings = BudgetSettings(
        minimum_reserve=Decimal("0.00"),
        currency_code="BRL",
        safe_spending_mode=SafeSpendingMode.UNTIL_NEXT_INCOME,
        include_pending_transactions=True,
        notification_thresholds={},
        timezone="America/Campo_Grande",
        telegram_notifications_enabled=False,
    )
    session.add(settings)
    session.flush()
    return settings


def local_today(timezone: str) -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()


def next_expected_income(session: Session, *, today: date) -> ExpectedIncome | None:
    return session.scalar(
        select(ExpectedIncome)
        .where(
            ExpectedIncome.deleted_at.is_(None),
            ExpectedIncome.status == ExpectedIncomeStatus.EXPECTED,
            ExpectedIncome.expected_date >= today,
        )
        .order_by(ExpectedIncome.expected_date, ExpectedIncome.id)
        .limit(1)
    )


def expenses_until(session: Session, *, today: date, end: date) -> list[PlannedCashFlow]:
    expenses = session.scalars(
        select(PlannedExpense).where(
            PlannedExpense.deleted_at.is_(None),
            PlannedExpense.status.in_([PlannedExpenseStatus.PLANNED, PlannedExpenseStatus.LATE]),
            PlannedExpense.due_date >= today,
            PlannedExpense.due_date <= end,
        )
    )
    return [
        PlannedCashFlow(
            amount=expense.expected_amount,
            due_date=expense.due_date,
            status=CashFlowStatus(expense.status.value),
            matched=expense.matched_transaction_id is not None,
        )
        for expense in expenses
    ]


def availability_values(
    session: Session,
    *,
    balance: Decimal,
    reserve: Decimal,
    today: date,
    income: ExpectedIncome | None,
) -> tuple[Decimal | None, Decimal | None, Decimal, Decimal]:
    if income is None:
        return None, None, Decimal("0.00"), Decimal("0.00")
    result = available_until_next_income(
        current_balance=balance,
        planned_expenses=expenses_until(session, today=today, end=income.expected_date),
        minimum_reserve=reserve,
        today=today,
        next_income_date=income.expected_date,
    )
    daily = safe_daily_limit(result.available, today=today, next_income_date=income.expected_date)
    return result.available, daily, result.committed_expenses, result.deficit
