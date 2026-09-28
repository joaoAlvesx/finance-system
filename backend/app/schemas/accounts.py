from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AccountType
from app.schemas.common import Money


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    institution_name: str | None = Field(default=None, max_length=120)
    type: AccountType
    currency_code: str = "BRL"
    initial_balance: Money

    @field_validator("currency_code")
    @classmethod
    def only_brl_in_mvp(cls, value: str) -> str:
        normalized = value.upper()
        if normalized != "BRL":
            raise ValueError("only BRL is supported in the MVP")
        return normalized


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    institution_name: str | None
    type: AccountType
    currency_code: str
    initial_balance: Money
    is_active: bool
    created_at: datetime
    updated_at: datetime
