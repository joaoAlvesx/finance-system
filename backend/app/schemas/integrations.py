from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SyncRunStatus, SyncTrigger
from app.schemas.common import Money


class PluggyConnectTokenRequest(BaseModel):
    item_id: str | None = Field(default=None, min_length=1, max_length=64)


class PluggyConnectTokenRead(BaseModel):
    connect_token: str


class PluggyItemRegister(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)


class PluggyAccountLinkRequest(BaseModel):
    account_id: UUID


class PluggySyncRequest(BaseModel):
    item_id: UUID | None = None
    full_reconciliation: bool = False


class PluggyAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    local_account_id: UUID | None
    external_account_id: str
    name: str
    account_type: str
    subtype: str | None
    currency_code: str
    balance: Money | None
    last_seen_at: datetime
    is_active: bool


class PluggyItemRead(BaseModel):
    id: UUID
    external_item_id: str
    connector_id: int | None
    connector_name: str | None
    status: str
    execution_status: str | None
    error_code: str | None
    requires_user_action: bool
    consent_expires_at: datetime | None
    last_successful_sync_at: datetime | None
    last_full_sync_at: datetime | None
    next_sync_at: datetime | None
    accounts: list[PluggyAccountRead]


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pluggy_item_id: UUID | None
    status: SyncRunStatus
    trigger: SyncTrigger
    full_reconciliation: bool
    started_at: datetime | None
    finished_at: datetime | None
    accounts_consulted: int
    created_count: int
    updated_count: int
    reconciled_count: int
    ignored_count: int
    error_code: str | None


class PluggyStatusRead(BaseModel):
    enabled: bool
    configured: bool
    connector_id: int
    include_sandbox: bool
    polling_seconds: int
    provider_refresh_note: str
    items: list[PluggyItemRead]
    latest_run: SyncRunRead | None


class PluggySyncQueuedRead(BaseModel):
    runs: list[SyncRunRead]
