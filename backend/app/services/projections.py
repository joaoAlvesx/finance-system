from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from app.services.money import CENT, money, non_negative_money, positive_money


class CashFlowStatus(StrEnum):
    EXPECTED = "expected"
    RECEIVED = "received"
    PLANNED = "planned"
    PAID = "paid"
    LATE = "late"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PlannedCashFlow:
    amount: Decimal
    due_date: date
    status: CashFlowStatus
    matched: bool = False


@dataclass(frozen=True, slots=True)
class Availability:
    available: Decimal
    deficit: Decimal
    committed_expenses: Decimal


def days_until_next_income(today: date, next_income_date: date) -> int:
    """Count today through the eve of income; an income tomorrow leaves one day."""

    if next_income_date < today:
        raise ValueError("next income date cannot be in the past")
    return max(1, (next_income_date - today).days)


def _sum_unpaid_expenses(expenses: Iterable[PlannedCashFlow], *, start: date, end: date) -> Decimal:
    total = Decimal("0.00")
    for expense in expenses:
        if expense.matched or expense.status not in {
            CashFlowStatus.PLANNED,
            CashFlowStatus.LATE,
        }:
            continue
        if start <= expense.due_date <= end:
            total += positive_money(expense.amount)
    return money(total)


def available_until_next_income(
    *,
    current_balance: Decimal,
    planned_expenses: Iterable[PlannedCashFlow],
    minimum_reserve: Decimal,
    today: date,
    next_income_date: date,
) -> Availability:
    if next_income_date < today:
        raise ValueError("next income date cannot be in the past")

    balance = money(current_balance)
    reserve = non_negative_money(minimum_reserve)
    committed = _sum_unpaid_expenses(planned_expenses, start=today, end=next_income_date)
    raw_available = money(balance - committed - reserve)
    return Availability(
        available=max(Decimal("0.00"), raw_available),
        deficit=max(Decimal("0.00"), -raw_available),
        committed_expenses=committed,
    )


def safe_daily_limit(available: Decimal, *, today: date, next_income_date: date) -> Decimal:
    normalized_available = non_negative_money(available)
    days = days_until_next_income(today, next_income_date)
    return (normalized_available / days).quantize(CENT, rounding=ROUND_DOWN)


def available_for_rest_of_month(
    *,
    current_balance: Decimal,
    expected_incomes: Iterable[PlannedCashFlow],
    planned_expenses: Iterable[PlannedCashFlow],
    minimum_reserve: Decimal,
    today: date,
) -> Decimal:
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    income_total = Decimal("0.00")
    for income in expected_incomes:
        if income.matched or income.status not in {
            CashFlowStatus.EXPECTED,
            CashFlowStatus.LATE,
        }:
            continue
        if month_start <= income.due_date <= month_end:
            income_total += positive_money(income.amount)

    expense_total = _sum_unpaid_expenses(planned_expenses, start=month_start, end=month_end)
    return money(
        money(current_balance) + income_total - expense_total - non_negative_money(minimum_reserve)
    )
