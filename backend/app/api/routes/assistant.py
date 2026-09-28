from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.core.service_auth import (
    READ_SCOPE,
    SIMULATE_SCOPE,
    SUGGEST_SCOPE,
    WRITE_SCOPE,
    ServicePrincipal,
    require_service_scope,
)
from app.db.base import utc_now
from app.models.account import Account
from app.models.assistant import AssistantInvocation, CategorySuggestion
from app.models.audit import AuditEvent
from app.models.category import Category
from app.models.enums import (
    AuditActorType,
    CategorySuggestionStatus,
    ClassificationMethod,
    TransactionSource,
    TransactionStatus,
)
from app.models.transaction import Transaction
from app.schemas.assistant import (
    AssistantTransaction,
    AvailabilityResult,
    BalanceResult,
    CategoryChangeRequest,
    CategorySuggestionCreate,
    CategorySuggestionDecision,
    CategorySuggestionRead,
    FutureExpenseListResult,
    InsightsResponse,
    ManualTransactionRequest,
    MonthlySummaryResult,
    NaturalLanguageRequest,
    NaturalLanguageResponse,
    PurchaseSimulationRequest,
    PurchaseSimulationResult,
    TransactionListResult,
)
from app.services.assistant import (
    availability_result,
    balance_result,
    future_expense_list,
    insight_cards,
    monthly_summary,
    natural_language_answer,
    purchase_simulation,
    transaction_list,
)
from app.services.dashboard import default_budget_settings, local_today
from app.services.deduplication import normalize_description, transaction_deduplication_hash

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _invocation(
    session: DatabaseSession,
    http_request: Request,
    principal: ServicePrincipal,
    tool_name: str,
) -> None:
    session.add(
        AssistantInvocation(
            service_token_id=principal.token_id,
            tool_name=tool_name,
            status="success",
            correlation_id=getattr(http_request.state, "correlation_id", None),
        )
    )


def _active_category(session: DatabaseSession, category_id: UUID) -> Category:
    category = session.get(Category, category_id)
    if category is None or not category.is_active:
        raise _error(404, "category_not_found", "Category was not found")
    return category


def _active_transaction(session: DatabaseSession, transaction_id: UUID) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.deleted_at is not None:
        raise _error(404, "transaction_not_found", "Transaction was not found")
    return transaction


def _suggestion_read(
    suggestion: CategorySuggestion, transaction: Transaction, category: Category
) -> CategorySuggestionRead:
    return CategorySuggestionRead(
        id=suggestion.id,
        transaction_id=transaction.id,
        transaction_description=transaction.description_raw,
        transaction_amount=transaction.amount,
        suggested_category_id=category.id,
        suggested_category_name=category.name,
        confidence=suggestion.confidence,
        rationale_code=suggestion.rationale_code,
        status=suggestion.status,
        suggested_by=suggestion.suggested_by,
        created_at=suggestion.created_at,
    )


@router.get("/tools/catalog")
def tool_catalog(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
) -> dict[str, object]:
    _invocation(session, http_request, principal, "catalog")
    session.commit()
    return {
        "tools": [
            {"name": "consultar_saldo", "scope": READ_SCOPE},
            {"name": "consultar_disponivel", "scope": READ_SCOPE},
            {"name": "listar_transacoes", "scope": READ_SCOPE, "max_records": 50},
            {"name": "listar_contas_futuras", "scope": READ_SCOPE, "max_records": 50},
            {"name": "registrar_transacao_manual", "scope": WRITE_SCOPE, "confirmation": True},
            {"name": "alterar_categoria", "scope": WRITE_SCOPE, "confirmation": True},
            {"name": "simular_gasto", "scope": SIMULATE_SCOPE},
            {"name": "gerar_resumo_mensal", "scope": READ_SCOPE},
        ]
    }


@router.get("/tools/balance", response_model=BalanceResult)
def tool_balance(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
    account_id: UUID | None = None,
) -> BalanceResult:
    try:
        result = balance_result(session, account_id=account_id)
    except LookupError as exc:
        raise _error(404, str(exc), "Account was not found") from exc
    _invocation(session, http_request, principal, "consultar_saldo")
    session.commit()
    return result


@router.get("/tools/availability", response_model=AvailabilityResult)
def tool_availability(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
) -> AvailabilityResult:
    result = availability_result(session)
    _invocation(session, http_request, principal, "consultar_disponivel")
    session.commit()
    return result


@router.get("/tools/transactions", response_model=TransactionListResult)
def tool_transactions(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
    date_from: date,
    date_to: date,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
) -> TransactionListResult:
    if date_from > date_to or (date_to - date_from).days > 366:
        raise _error(422, "invalid_date_range", "Date range must be at most 366 days")
    result = transaction_list(
        session,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        category_id=category_id,
        search=search,
        limit=limit,
    )
    _invocation(session, http_request, principal, "listar_transacoes")
    session.commit()
    return result


@router.get("/tools/future-expenses", response_model=FutureExpenseListResult)
def tool_future_expenses(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
    date_from: date,
    date_to: date,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> FutureExpenseListResult:
    if date_from > date_to or (date_to - date_from).days > 366:
        raise _error(422, "invalid_date_range", "Date range must be at most 366 days")
    result = future_expense_list(session, start=date_from, end=date_to, limit=limit)
    _invocation(session, http_request, principal, "listar_contas_futuras")
    session.commit()
    return result


@router.get("/tools/monthly-summary", response_model=MonthlySummaryResult)
def tool_monthly_summary(
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(READ_SCOPE))],
    year: Annotated[int, Query(ge=2000, le=2200)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> MonthlySummaryResult:
    result = monthly_summary(session, year=year, month=month)
    _invocation(session, http_request, principal, "gerar_resumo_mensal")
    session.commit()
    return result


@router.post("/tools/purchase-simulation", response_model=PurchaseSimulationResult)
def tool_purchase_simulation(
    request: PurchaseSimulationRequest,
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(SIMULATE_SCOPE))],
) -> PurchaseSimulationResult:
    result = purchase_simulation(session, amount=request.amount)
    _invocation(session, http_request, principal, "simular_gasto")
    session.commit()
    return result


@router.post(
    "/tools/manual-transactions",
    response_model=AssistantTransaction,
    status_code=status.HTTP_201_CREATED,
)
def tool_manual_transaction(
    request: ManualTransactionRequest,
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(WRITE_SCOPE))],
) -> AssistantTransaction:
    if not request.confirmed:
        raise _error(409, "confirmation_required", "Explicit confirmation is required")
    account = session.get(Account, request.account_id)
    if account is None or account.deleted_at is not None or not account.is_active:
        raise _error(404, "account_not_found", "Account was not found")
    category = _active_category(session, request.category_id) if request.category_id else None
    transaction = Transaction(
        account_id=request.account_id,
        type=request.type,
        direction=request.direction,
        status=TransactionStatus.POSTED,
        amount=request.amount,
        transaction_date=request.transaction_date,
        description_raw=request.description.strip(),
        description_normalized=normalize_description(request.description),
        category_id=request.category_id,
        source=TransactionSource.MANUAL,
        classification_method=ClassificationMethod.MANUAL,
        is_reviewed=True,
        deduplication_hash=transaction_deduplication_hash(
            account_id=request.account_id,
            transaction_date=request.transaction_date,
            description=request.description,
            amount=request.amount,
            direction=request.direction.value,
        ),
    )
    session.add(transaction)
    session.flush()
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="transaction_created_by_service",
            changed_fields=[
                "account_id", "type", "direction", "amount", "transaction_date",
                "description_raw", "category_id",
            ],
            actor_type=AuditActorType.SERVICE,
            actor_identifier=principal.name,
            correlation_id=getattr(http_request.state, "correlation_id", None),
        )
    )
    _invocation(session, http_request, principal, "registrar_transacao_manual")
    session.commit()
    return AssistantTransaction(
        id=transaction.id,
        account_id=transaction.account_id,
        transaction_date=transaction.transaction_date,
        description=transaction.description_raw,
        amount=transaction.amount,
        direction=transaction.direction,
        type=transaction.type,
        status=transaction.status,
        category_id=transaction.category_id,
        category_name=category.name if category else None,
    )


@router.post("/tools/transactions/{transaction_id}/category", response_model=AssistantTransaction)
def tool_change_category(
    transaction_id: UUID,
    request: CategoryChangeRequest,
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(WRITE_SCOPE))],
) -> AssistantTransaction:
    if not request.confirmed:
        raise _error(409, "confirmation_required", "Explicit confirmation is required")
    transaction = _active_transaction(session, transaction_id)
    category = _active_category(session, request.category_id)
    before = transaction.category_id
    transaction.category_id = category.id
    transaction.classification_method = ClassificationMethod.MANUAL
    transaction.is_reviewed = True
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action="category_changed_by_service",
            changed_fields=["category_id", "classification_method", "is_reviewed"],
            change_data={
                "category_id": {
                    "before": str(before) if before else None,
                    "after": str(category.id),
                }
            },
            actor_type=AuditActorType.SERVICE,
            actor_identifier=principal.name,
            correlation_id=getattr(http_request.state, "correlation_id", None),
        )
    )
    _invocation(session, http_request, principal, "alterar_categoria")
    session.commit()
    return AssistantTransaction(
        id=transaction.id,
        account_id=transaction.account_id,
        transaction_date=transaction.transaction_date,
        description=transaction.description_raw,
        amount=transaction.amount,
        direction=transaction.direction,
        type=transaction.type,
        status=transaction.status,
        category_id=transaction.category_id,
        category_name=category.name,
    )


@router.post(
    "/tools/category-suggestions",
    response_model=CategorySuggestionRead,
    status_code=status.HTTP_201_CREATED,
)
def tool_suggest_category(
    request: CategorySuggestionCreate,
    session: DatabaseSession,
    http_request: Request,
    principal: Annotated[ServicePrincipal, Depends(require_service_scope(SUGGEST_SCOPE))],
) -> CategorySuggestionRead:
    transaction = _active_transaction(session, request.transaction_id)
    category = _active_category(session, request.category_id)
    existing = session.scalar(
        select(CategorySuggestion).where(
            CategorySuggestion.transaction_id == transaction.id,
            CategorySuggestion.status == CategorySuggestionStatus.PENDING,
            CategorySuggestion.deleted_at.is_(None),
        )
    )
    if existing:
        existing.suggested_category_id = category.id
        existing.confidence = request.confidence
        existing.rationale_code = request.rationale_code
        existing.suggested_by = principal.name
        suggestion = existing
    else:
        suggestion = CategorySuggestion(
            transaction_id=transaction.id,
            suggested_category_id=category.id,
            confidence=request.confidence,
            rationale_code=request.rationale_code,
            status=CategorySuggestionStatus.PENDING,
            suggested_by=principal.name,
        )
        session.add(suggestion)
    session.flush()
    _invocation(session, http_request, principal, "sugerir_categoria")
    session.commit()
    return _suggestion_read(suggestion, transaction, category)


@router.post("/query", response_model=NaturalLanguageResponse)
def query_assistant(
    request: NaturalLanguageRequest, session: DatabaseSession
) -> NaturalLanguageResponse:
    result = natural_language_answer(session, request.question)
    session.commit()
    return result


@router.get("/insights", response_model=InsightsResponse)
def get_insights(session: DatabaseSession) -> InsightsResponse:
    result = insight_cards(session)
    session.commit()
    return result


@router.get("/suggestions", response_model=list[CategorySuggestionRead])
def list_suggestions(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> list[CategorySuggestionRead]:
    rows = session.execute(
        select(CategorySuggestion, Transaction, Category)
        .join(Transaction, Transaction.id == CategorySuggestion.transaction_id)
        .join(Category, Category.id == CategorySuggestion.suggested_category_id)
        .where(
            CategorySuggestion.deleted_at.is_(None),
            CategorySuggestion.status == CategorySuggestionStatus.PENDING,
            Transaction.deleted_at.is_(None),
        )
        .order_by(CategorySuggestion.created_at.desc())
        .limit(limit)
    )
    return [
        _suggestion_read(suggestion, transaction, category)
        for suggestion, transaction, category in rows
    ]


@router.post("/suggestions/{suggestion_id}/decision", response_model=CategorySuggestionRead)
def decide_suggestion(
    suggestion_id: UUID,
    request: CategorySuggestionDecision,
    session: DatabaseSession,
) -> CategorySuggestionRead:
    suggestion = session.scalar(
        select(CategorySuggestion).where(CategorySuggestion.id == suggestion_id).with_for_update()
    )
    if (
        suggestion is None
        or suggestion.deleted_at is not None
        or suggestion.status != CategorySuggestionStatus.PENDING
    ):
        raise _error(404, "suggestion_not_found", "Pending suggestion was not found")
    transaction = _active_transaction(session, suggestion.transaction_id)
    category = _active_category(session, suggestion.suggested_category_id)
    suggestion.reviewed_at = utc_now()
    if request.decision == "accept":
        before = transaction.category_id
        transaction.category_id = category.id
        transaction.classification_method = ClassificationMethod.AI
        transaction.classification_confidence = suggestion.confidence
        transaction.is_reviewed = True
        suggestion.status = CategorySuggestionStatus.ACCEPTED
        action = "category_suggestion_accepted"
        change_data: dict[str, object] = {
            "category_id": {
                "before": str(before) if before else None,
                "after": str(category.id),
            },
            "suggestion_id": str(suggestion.id),
        }
    else:
        suggestion.status = CategorySuggestionStatus.REJECTED
        action = "category_suggestion_rejected"
        change_data = {"suggestion_id": str(suggestion.id)}
    session.add(
        AuditEvent(
            aggregate_type="transaction",
            aggregate_id=transaction.id,
            action=action,
            changed_fields=["category_id", "classification_method", "is_reviewed"]
            if request.decision == "accept"
            else [],
            change_data=change_data,
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )
    session.commit()
    return _suggestion_read(suggestion, transaction, category)


@router.get("/defaults")
def assistant_defaults(session: DatabaseSession) -> dict[str, str]:
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    return {
        "today": today.isoformat(),
        "transaction_date_from": today.replace(day=1).isoformat(),
        "transaction_date_to": today.isoformat(),
        "future_date_to": (today + timedelta(days=45)).isoformat(),
    }
