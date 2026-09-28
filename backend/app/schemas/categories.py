from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind, RuleMatchField


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: UUID | None = None
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=80)
    kind: CategoryKind


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None
    color: str | None
    icon: str | None
    kind: CategoryKind
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryRuleCreate(BaseModel):
    match_field: RuleMatchField = RuleMatchField.DESCRIPTION
    pattern: str = Field(min_length=1, max_length=500)
    category_id: UUID
    priority: int = Field(default=100, ge=0, le=10_000)
    account_id: UUID | None = None


class CategoryRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    match_field: RuleMatchField
    pattern: str
    category_id: UUID
    priority: int
    account_id: UUID | None
    hit_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
