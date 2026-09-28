from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.db.base import utc_now
from app.models.account import Account, BalanceSnapshot
from app.models.audit import AuditEvent
from app.models.enums import AuditActorType, BalanceSnapshotSource
from app.schemas.accounts import AccountCreate, AccountRead

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
def list_accounts(
    session: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[Account]:
    statement = select(Account).where(Account.deleted_at.is_(None)).order_by(Account.name)
    if not include_inactive:
        statement = statement.where(Account.is_active.is_(True))
    return list(session.scalars(statement))


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(request: AccountCreate, session: DatabaseSession) -> Account:
    account = Account(
        name=request.name.strip(),
        institution_name=(request.institution_name or "").strip() or None,
        type=request.type,
        currency_code=request.currency_code,
        initial_balance=request.initial_balance,
        is_active=True,
    )
    session.add(account)
    session.flush()
    session.add(
        BalanceSnapshot(
            account_id=account.id,
            amount=request.initial_balance,
            currency_code=request.currency_code,
            source=BalanceSnapshotSource.INITIAL,
            observed_at=utc_now(),
            external_id=f"initial:{account.id}",
        )
    )
    session.add(
        AuditEvent(
            aggregate_type="account",
            aggregate_id=account.id,
            action="account_created",
            changed_fields=["name", "institution_name", "type", "currency_code", "initial_balance"],
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    session.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: UUID, session: DatabaseSession) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": "Account was not found"},
        )
    return account
