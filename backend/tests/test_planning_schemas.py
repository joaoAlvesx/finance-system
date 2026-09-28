from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.enums import ExpectedIncomeStatus, PlannedExpenseStatus
from app.schemas.planning import (
    BudgetSettingsUpdate,
    ExpectedIncomePatch,
    PlannedExpensePatch,
)


def test_budget_reserve_uses_decimal_and_rejects_float() -> None:
    settings = BudgetSettingsUpdate(minimum_reserve="125.50")
    assert settings.minimum_reserve == Decimal("125.50")

    with pytest.raises(ValidationError):
        BudgetSettingsUpdate(minimum_reserve=125.5)


def test_received_and_paid_states_require_transaction_reconciliation() -> None:
    with pytest.raises(ValidationError):
        ExpectedIncomePatch(status=ExpectedIncomeStatus.RECEIVED)
    with pytest.raises(ValidationError):
        PlannedExpensePatch(status=PlannedExpenseStatus.PAID)
