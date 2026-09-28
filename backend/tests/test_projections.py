from datetime import date
from decimal import Decimal

import pytest

from app.services.projections import (
    CashFlowStatus,
    PlannedCashFlow,
    available_for_rest_of_month,
    available_until_next_income,
    days_until_next_income,
    safe_daily_limit,
)


def flow(
    amount: str,
    due_date: date,
    status: CashFlowStatus,
    *,
    matched: bool = False,
) -> PlannedCashFlow:
    return PlannedCashFlow(
        amount=Decimal(amount), due_date=due_date, status=status, matched=matched
    )


def test_available_uses_snapshot_balance_and_only_unpaid_commitments() -> None:
    today = date(2026, 9, 10)
    result = available_until_next_income(
        current_balance=Decimal("1000.00"),
        planned_expenses=[
            flow("200", date(2026, 9, 11), CashFlowStatus.PLANNED),
            flow("50", date(2026, 9, 12), CashFlowStatus.LATE),
            flow("90", date(2026, 9, 12), CashFlowStatus.PAID, matched=True),
            flow("70", date(2026, 9, 16), CashFlowStatus.PLANNED),
        ],
        minimum_reserve=Decimal("300.00"),
        today=today,
        next_income_date=date(2026, 9, 15),
    )

    assert result.available == Decimal("450.00")
    assert result.deficit == Decimal("0.00")
    assert result.committed_expenses == Decimal("250.00")


def test_deficit_is_separate_when_reserve_exceeds_balance() -> None:
    result = available_until_next_income(
        current_balance=Decimal("100.00"),
        planned_expenses=[],
        minimum_reserve=Decimal("150.00"),
        today=date(2026, 9, 10),
        next_income_date=date(2026, 9, 11),
    )

    assert result.available == Decimal("0.00")
    assert result.deficit == Decimal("50.00")


def test_tomorrow_means_one_remaining_day_and_rounds_down() -> None:
    today = date(2026, 9, 10)
    tomorrow = date(2026, 9, 11)

    assert days_until_next_income(today, tomorrow) == 1
    assert safe_daily_limit(Decimal("10.00"), today=today, next_income_date=tomorrow) == Decimal(
        "10.00"
    )
    assert safe_daily_limit(
        Decimal("10.00"), today=today, next_income_date=date(2026, 9, 13)
    ) == Decimal("3.33")


def test_same_day_income_uses_minimum_one_day() -> None:
    today = date(2026, 9, 10)
    assert days_until_next_income(today, today) == 1


def test_past_date_is_not_a_next_income() -> None:
    with pytest.raises(ValueError):
        days_until_next_income(date(2026, 9, 10), date(2026, 9, 9))


def test_month_projection_handles_year_boundary_and_variable_income() -> None:
    result = available_for_rest_of_month(
        current_balance=Decimal("500.00"),
        expected_incomes=[
            flow("700", date(2026, 12, 15), CashFlowStatus.EXPECTED),
            flow("1600", date(2027, 1, 2), CashFlowStatus.EXPECTED),
            flow("650", date(2026, 12, 5), CashFlowStatus.RECEIVED, matched=True),
        ],
        planned_expenses=[
            flow("250", date(2026, 12, 20), CashFlowStatus.PLANNED),
            flow("100", date(2027, 1, 1), CashFlowStatus.PLANNED),
        ],
        minimum_reserve=Decimal("300.00"),
        today=date(2026, 12, 10),
    )

    assert result == Decimal("650.00")
