from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("money must be sent as a decimal string, never as float")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(max_digits=14, decimal_places=2),
]
PositiveMoney = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(gt=0, max_digits=14, decimal_places=2),
]
