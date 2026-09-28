from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.enums import AccountType, TransactionDirection, TransactionType
from app.schemas.accounts import AccountCreate
from app.schemas.transactions import TransactionCreate


def test_money_rejects_json_style_float() -> None:
    with pytest.raises(ValidationError, match="never as float"):
        AccountCreate(
            name="Conta",
            type=AccountType.CHECKING,
            initial_balance=10.25,
        )


def test_money_accepts_decimal_string() -> None:
    account = AccountCreate(
        name="Conta",
        type=AccountType.CHECKING,
        initial_balance="10.25",
    )
    assert account.initial_balance == Decimal("10.25")


def test_manual_transaction_rejects_inconsistent_direction() -> None:
    with pytest.raises(ValidationError, match="income/credit or expense/debit"):
        TransactionCreate(
            account_id=UUID("00000000-0000-0000-0000-000000000001"),
            type=TransactionType.EXPENSE,
            direction=TransactionDirection.CREDIT,
            amount="10.00",
            transaction_date="2026-01-01",
            description="Teste",
        )
