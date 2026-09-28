from decimal import Decimal
from uuid import UUID

import pytest

from app.services.ledger import (
    LedgerDirection,
    LedgerEntry,
    LedgerStatus,
    LedgerType,
    TransferLeg,
    consolidated_totals,
    validate_transfer_pair,
)


def test_own_transfers_do_not_change_consolidated_income_or_expense() -> None:
    totals = consolidated_totals(
        [
            LedgerEntry(Decimal("1000"), LedgerType.INCOME, LedgerDirection.CREDIT),
            LedgerEntry(Decimal("100"), LedgerType.EXPENSE, LedgerDirection.DEBIT),
            LedgerEntry(Decimal("300"), LedgerType.TRANSFER, LedgerDirection.DEBIT),
            LedgerEntry(Decimal("300"), LedgerType.TRANSFER, LedgerDirection.CREDIT),
        ]
    )

    assert totals.income == Decimal("1000.00")
    assert totals.expense == Decimal("100.00")


def test_pending_and_soft_deleted_entries_are_filtered() -> None:
    entries = [
        LedgerEntry(
            Decimal("20"),
            LedgerType.EXPENSE,
            LedgerDirection.DEBIT,
            LedgerStatus.PENDING,
        ),
        LedgerEntry(
            Decimal("80"),
            LedgerType.EXPENSE,
            LedgerDirection.DEBIT,
            deleted=True,
        ),
    ]

    assert consolidated_totals(entries, include_pending=False).expense == Decimal("0.00")
    assert consolidated_totals(entries, include_pending=True).expense == Decimal("20.00")


def test_inconsistent_type_and_direction_is_rejected() -> None:
    with pytest.raises(ValueError):
        consolidated_totals([LedgerEntry(Decimal("10"), LedgerType.INCOME, LedgerDirection.DEBIT)])


def test_transfer_pair_requires_equal_opposite_legs_in_distinct_accounts() -> None:
    group_id = UUID("00000000-0000-0000-0000-000000000001")
    first_account = UUID("00000000-0000-0000-0000-000000000010")
    second_account = UUID("00000000-0000-0000-0000-000000000020")
    validate_transfer_pair(
        [
            TransferLeg(first_account, group_id, Decimal("300"), LedgerDirection.DEBIT),
            TransferLeg(second_account, group_id, Decimal("300"), LedgerDirection.CREDIT),
        ]
    )

    with pytest.raises(ValueError):
        validate_transfer_pair(
            [
                TransferLeg(first_account, group_id, Decimal("300"), LedgerDirection.DEBIT),
                TransferLeg(second_account, group_id, Decimal("299"), LedgerDirection.CREDIT),
            ]
        )
