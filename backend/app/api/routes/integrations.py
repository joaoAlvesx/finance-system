from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.core.config import Settings, get_settings
from app.integrations.pluggy import PluggyAPIError, PluggyClient
from app.models.integration import PluggyAccountLink, PluggyItem, SyncRun
from app.schemas.integrations import (
    PluggyAccountLinkRequest,
    PluggyAccountRead,
    PluggyConnectTokenRead,
    PluggyConnectTokenRequest,
    PluggyItemRead,
    PluggyItemRegister,
    PluggyStatusRead,
    PluggySyncQueuedRead,
    PluggySyncRequest,
    SyncRunRead,
)
from app.services.pluggy_sync import (
    link_pluggy_account,
    queue_manual_syncs,
    register_pluggy_item,
)

router = APIRouter(prefix="/integrations/pluggy", tags=["integrations"])


def build_pluggy_client(settings: Settings) -> PluggyClient:
    client_id = settings.pluggy_client_id.get_secret_value().strip()
    client_secret = settings.pluggy_client_secret.get_secret_value().strip()
    if not settings.pluggy_enabled or not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "pluggy_not_configured",
                "message": "A integração Pluggy ainda não está configurada no servidor.",
            },
        )
    return PluggyClient(
        client_id=client_id,
        client_secret=client_secret,
        base_url=settings.pluggy_api_base_url,
        request_timeout=settings.pluggy_request_timeout_seconds,
    )


def _provider_error(exc: PluggyAPIError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": exc.code,
            "message": "A Pluggy não concluiu a solicitação. Tente novamente mais tarde.",
        },
    )


@router.get("/status", response_model=PluggyStatusRead)
def pluggy_status(session: DatabaseSession) -> PluggyStatusRead:
    settings = get_settings()
    items = list(
        session.scalars(
            select(PluggyItem)
            .where(PluggyItem.deleted_at.is_(None))
            .order_by(PluggyItem.created_at)
        )
    )
    links = list(
        session.scalars(
            select(PluggyAccountLink)
            .where(PluggyAccountLink.deleted_at.is_(None))
            .order_by(PluggyAccountLink.name)
        )
    )
    links_by_item: dict[object, list[PluggyAccountRead]] = {}
    for link in links:
        links_by_item.setdefault(link.pluggy_item_id, []).append(
            PluggyAccountRead.model_validate(link)
        )
    latest_run = session.scalar(
        select(SyncRun)
        .where(SyncRun.integration == "pluggy")
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    )
    item_reads = [
        PluggyItemRead(
            id=item.id,
            external_item_id=item.external_item_id,
            connector_id=item.connector_id,
            connector_name=item.connector_name,
            status=item.status,
            execution_status=item.execution_status,
            error_code=item.error_code,
            requires_user_action=item.requires_user_action,
            consent_expires_at=item.consent_expires_at,
            last_successful_sync_at=item.last_successful_sync_at,
            last_full_sync_at=item.last_full_sync_at,
            next_sync_at=item.next_sync_at,
            accounts=links_by_item.get(item.id, []),
        )
        for item in items
    ]
    configured = bool(
        settings.pluggy_enabled
        and settings.pluggy_client_id.get_secret_value().strip()
        and settings.pluggy_client_secret.get_secret_value().strip()
    )
    return PluggyStatusRead(
        enabled=settings.pluggy_enabled,
        configured=configured,
        connector_id=settings.pluggy_connector_id,
        include_sandbox=settings.pluggy_include_sandbox,
        polling_seconds=settings.pluggy_poll_seconds,
        provider_refresh_note=(
            "O polling detecta dados disponíveis na Pluggy. No Meu Pluggy gratuito, "
            "a atualização da origem ocorre normalmente uma vez ao dia."
        ),
        items=item_reads,
        latest_run=SyncRunRead.model_validate(latest_run) if latest_run else None,
    )


@router.post("/connect-token", response_model=PluggyConnectTokenRead)
def create_connect_token(request: PluggyConnectTokenRequest) -> PluggyConnectTokenRead:
    settings = get_settings()
    client = build_pluggy_client(settings)
    try:
        token = client.create_connect_token(
            client_user_id=settings.pluggy_client_user_id,
            item_id=request.item_id,
        )
    except PluggyAPIError as exc:
        raise _provider_error(exc) from None
    return PluggyConnectTokenRead(connect_token=token)


@router.post("/items", response_model=PluggyItemRead, status_code=status.HTTP_201_CREATED)
def register_item(request: PluggyItemRegister, session: DatabaseSession) -> PluggyItemRead:
    settings = get_settings()
    client = build_pluggy_client(settings)
    try:
        item = register_pluggy_item(
            session,
            client,
            external_item_id=request.item_id.strip(),
            poll_seconds=settings.pluggy_poll_seconds,
        )
    except PluggyAPIError as exc:
        raise _provider_error(exc) from None
    links = list(
        session.scalars(
            select(PluggyAccountLink)
            .where(
                PluggyAccountLink.pluggy_item_id == item.id,
                PluggyAccountLink.deleted_at.is_(None),
            )
            .order_by(PluggyAccountLink.name)
        )
    )
    return PluggyItemRead(
        id=item.id,
        external_item_id=item.external_item_id,
        connector_id=item.connector_id,
        connector_name=item.connector_name,
        status=item.status,
        execution_status=item.execution_status,
        error_code=item.error_code,
        requires_user_action=item.requires_user_action,
        consent_expires_at=item.consent_expires_at,
        last_successful_sync_at=item.last_successful_sync_at,
        last_full_sync_at=item.last_full_sync_at,
        next_sync_at=item.next_sync_at,
        accounts=[PluggyAccountRead.model_validate(link) for link in links],
    )


@router.post("/accounts/{link_id}/link", response_model=PluggyAccountRead)
def link_account(
    link_id: UUID,
    request: PluggyAccountLinkRequest,
    session: DatabaseSession,
) -> PluggyAccountLink:
    try:
        return link_pluggy_account(
            session,
            link_id=link_id,
            local_account_id=request.account_id,
        )
    except (LookupError, ValueError) as exc:
        code = str(exc)
        response_status = (
            status.HTTP_404_NOT_FOUND if code.endswith("not_found") else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=response_status,
            detail={"code": code, "message": "Não foi possível vincular esta conta."},
        ) from None


@router.post("/sync", response_model=PluggySyncQueuedRead, status_code=status.HTTP_202_ACCEPTED)
def request_sync(request: PluggySyncRequest, session: DatabaseSession) -> PluggySyncQueuedRead:
    try:
        runs = queue_manual_syncs(
            session,
            item_id=request.item_id,
            full_reconciliation=request.full_reconciliation,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": str(exc), "message": "Conexão Pluggy não encontrada."},
        ) from None
    return PluggySyncQueuedRead(runs=[SyncRunRead.model_validate(run) for run in runs])
