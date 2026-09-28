from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Normalize a monetary value to cents while refusing binary floating point."""

    if isinstance(value, bool | float):
        raise TypeError("money values must use Decimal, int, or str")
    try:
        normalized = Decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc
    if not normalized.is_finite():
        raise ValueError("money values must be finite")
    return normalized


def positive_money(value: Decimal | int | str) -> Decimal:
    normalized = money(value)
    if normalized <= 0:
        raise ValueError("money value must be positive")
    return normalized


def non_negative_money(value: Decimal | int | str) -> Decimal:
    normalized = money(value)
    if normalized < 0:
        raise ValueError("money value must be non-negative")
    return normalized
