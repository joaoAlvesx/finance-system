from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.services.money import money


@dataclass(frozen=True, slots=True)
class BalancePoint:
    amount: Decimal
    observed_at: datetime
    reliable: bool = True


def latest_reliable_balance(snapshots: Iterable[BalancePoint]) -> BalancePoint:
    reliable = [snapshot for snapshot in snapshots if snapshot.reliable]
    if not reliable:
        raise ValueError("at least one reliable balance snapshot is required")
    latest = max(reliable, key=lambda snapshot: snapshot.observed_at)
    return BalancePoint(amount=money(latest.amount), observed_at=latest.observed_at, reliable=True)
