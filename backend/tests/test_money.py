from decimal import Decimal

import pytest

from app.services.money import money, non_negative_money, positive_money


def test_money_normalizes_to_two_decimal_places() -> None:
    assert money("10.126") == Decimal("10.13")
    assert money(10) == Decimal("10.00")


def test_money_rejects_float_and_non_finite_values() -> None:
    with pytest.raises(TypeError):
        money(10.2)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        money("NaN")


def test_sign_specific_validators() -> None:
    with pytest.raises(ValueError):
        positive_money("0")
    with pytest.raises(ValueError):
        non_negative_money("-0.01")
