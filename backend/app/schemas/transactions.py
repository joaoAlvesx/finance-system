from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    TransactionDirection,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.schemas.common import PositiveMoney


class TransactionCreate(BaseModel):
    account_id: UUID
    type: TransactionType
    direction: TransactionDirection
    status: TransactionStatus = TransactionStatus.POSTED
    amount: PositiveMoney
    transaction_date: date
    description: str = Field(min_length=1, max_length=1000)
    category_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def type_and_direction_match(self) -> "TransactionCreate":
        valid = (
            self.type == TransactionType.INCOME and self.direction == TransactionDirection.CREDIT
        ) or (self.type == TransactionType.EXPENSE and self.direction == TransactionDirection.DEBIT)
        if not valid:
            raise ValueError("manual transactions must be income/credit or expense/debit")
        return self


class TransferCreate(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: PositiveMoney
    transaction_date: date
    description: str = Field(default="Transferência entre contas", min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def accounts_are_distinct(self) -> "TransferCreate":
        if self.from_account_id == self.to_account_id:
            raise ValueError("transfer accounts must be distinct")
        return self


class TransactionPatch(BaseModel):
    category_id: UUID | None = None
    status: TransactionStatus | None = None
    is_reviewed: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SimilarTransactionsCategoryUpdate(BaseModel):
    category_id: UUID
    create_rule: bool = True


class SimilarTransactionsCategoryResult(BaseModel):
    category_id: UUID
    updated_count: int
    rule_created: bool


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    type: TransactionType
    direction: TransactionDirection
    status: TransactionStatus
    amount: PositiveMoney
    transaction_date: date
    posted_at: datetime | None
    description_raw: str
    description_normalized: str
    merchant_name: str | None
    category_id: UUID | None
    source: TransactionSource
    classification_method: str
    is_reviewed: bool
    notes: str | None
    transfer_group_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    next_cursor: str | None


class TransferRead(BaseModel):
    transfer_group_id: UUID
    debit: TransactionRead
    credit: TransactionRead
