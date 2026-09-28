from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExternalItem:
    id: str
    connector_id: int | None
    connector_name: str | None
    status: str
    execution_status: str | None
    error_code: str | None
    consent_expires_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExternalAccount:
    id: str
    item_id: str
    name: str
    type: str
    subtype: str | None
    currency_code: str
    balance: Decimal | None


@dataclass(frozen=True, slots=True)
class ExternalTransaction:
    id: str
    account_id: str
    description: str
    description_raw: str | None
    amount: Decimal
    currency_code: str
    date: datetime
    type: str | None
    status: str
    merchant_name: str | None
    provider_category: str | None


@dataclass(frozen=True, slots=True)
class TransactionPage:
    transactions: list[ExternalTransaction]
    next_cursor: str | None


class BankDataProvider(Protocol):
    def create_connect_token(self, *, client_user_id: str, item_id: str | None = None) -> str: ...

    def get_item(self, item_id: str) -> ExternalItem: ...

    def trigger_item_update(self, item_id: str) -> None: ...

    def list_accounts(self, item_id: str) -> list[ExternalAccount]: ...

    def list_transactions(
        self,
        account_id: str,
        *,
        cursor: str | None = None,
        created_at_from: datetime | None = None,
    ) -> TransactionPage: ...
