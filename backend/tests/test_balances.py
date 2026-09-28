from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.balances import BalancePoint, latest_reliable_balance


def test_projection_starts_from_latest_reliable_snapshot() -> None:
    selected = latest_reliable_balance(
        [
            BalancePoint(Decimal("100"), datetime(2026, 9, 10, 10, tzinfo=UTC)),
            BalancePoint(
                Decimal("999"),
                datetime(2026, 9, 10, 12, tzinfo=UTC),
                reliable=False,
            ),
            BalancePoint(Decimal("120"), datetime(2026, 9, 10, 11, tzinfo=UTC)),
        ]
    )

    assert selected.amount == Decimal("120.00")
    assert selected.observed_at == datetime(2026, 9, 10, 11, tzinfo=UTC)


def test_projection_requires_a_reliable_snapshot() -> None:
    with pytest.raises(ValueError):
        latest_reliable_balance([])
