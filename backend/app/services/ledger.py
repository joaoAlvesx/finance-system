from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.services.money import money, positive_money


class LedgerType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class LedgerDirection(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class LedgerStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    amount: Decimal
    type: LedgerType
    direction: LedgerDirection
    status: LedgerStatus = LedgerStatus.POSTED
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class ConsolidatedTotals:
    income: Decimal
    expense: Decimal


@dataclass(frozen=True, slots=True)
class TransferLeg:
    account_id: UUID
    transfer_group_id: UUID
    amount: Decimal
    direction: LedgerDirection


def validate_transfer_pair(legs: Iterable[TransferLeg]) -> None:
    pair = list(legs)
    if len(pair) != 2:
        raise ValueError("a transfer must have exactly two legs")
    if pair[0].transfer_group_id != pair[1].transfer_group_id:
        raise ValueError("transfer legs must share a group")
    if pair[0].account_id == pair[1].account_id:
        raise ValueError("transfer legs must use distinct accounts")
    if positive_money(pair[0].amount) != positive_money(pair[1].amount):
        raise ValueError("transfer legs must have equal amounts")
    if {pair[0].direction, pair[1].direction} != {
        LedgerDirection.CREDIT,
        LedgerDirection.DEBIT,
    }:
        raise ValueError("a transfer must have one credit and one debit")


def consolidated_totals(
    entries: Iterable[LedgerEntry], *, include_pending: bool = True
) -> ConsolidatedTotals:
    income = Decimal("0.00")
    expense = Decimal("0.00")

    for entry in entries:
        if entry.deleted or entry.status == LedgerStatus.IGNORED:
            continue
        if entry.status == LedgerStatus.PENDING and not include_pending:
            continue
        amount = positive_money(entry.amount)
        if entry.type == LedgerType.TRANSFER:
            continue
        if entry.type == LedgerType.INCOME and entry.direction == LedgerDirection.CREDIT:
            income += amount
        elif entry.type == LedgerType.EXPENSE and entry.direction == LedgerDirection.DEBIT:
            expense += amount
        else:
            raise ValueError("ledger type and direction are inconsistent")

    return ConsolidatedTotals(income=money(income), expense=money(expense))
