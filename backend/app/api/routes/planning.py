from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.db.base import utc_now
from app.models.audit import AuditEvent
from app.models.category import Category
from app.models.enums import AuditActorType, ExpectedIncomeStatus, PlannedExpenseStatus
from app.models.planning import ExpectedIncome, PlannedExpense
from app.models.settings import BudgetSettings
from app.schemas.planning import (
    BudgetSettingsRead,
    BudgetSettingsUpdate,
    ExpectedIncomeCreate,
    ExpectedIncomePatch,
    ExpectedIncomeRead,
    PlannedExpenseCreate,
    PlannedExpensePatch,
    PlannedExpenseRead,
)
from app.services.dashboard import default_budget_settings

router = APIRouter(prefix="/planning", tags=["planning"])


def _not_found(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": code, "message": "Planning item was not found"},
    )


def _audit(
    session: DatabaseSession,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    action: str,
    changed_fields: list[str],
) -> None:
    session.add(
        AuditEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action=action,
            changed_fields=changed_fields,
            actor_type=AuditActorType.USER,
            actor_identifier="local-user",
        )
    )


def _validate_category(session: DatabaseSession, category_id: UUID | None) -> None:
    if category_id is None:
        return
    category = session.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "category_not_found", "message": "Category was not found"},
        )


@router.get("/incomes", response_model=list[ExpectedIncomeRead])
def list_expected_incomes(
    session: DatabaseSession,
    include_cancelled: Annotated[bool, Query()] = False,
) -> list[ExpectedIncome]:
    statement = select(ExpectedIncome).where(ExpectedIncome.deleted_at.is_(None))
    if not include_cancelled:
        statement = statement.where(ExpectedIncome.status != ExpectedIncomeStatus.CANCELLED)
    return list(
        session.scalars(statement.order_by(ExpectedIncome.expected_date, ExpectedIncome.id))
    )


@router.post("/incomes", response_model=ExpectedIncomeRead, status_code=status.HTTP_201_CREATED)
def create_expected_income(
    request: ExpectedIncomeCreate, session: DatabaseSession
) -> ExpectedIncome:
    income = ExpectedIncome(
        name=request.name.strip(),
        expected_amount=request.expected_amount,
        expected_date=request.expected_date,
        recurrence=request.recurrence,
        amount_is_variable=request.amount_is_variable,
        status=ExpectedIncomeStatus.EXPECTED,
    )
    session.add(income)
    session.flush()
    _audit(
        session,
        aggregate_type="expected_income",
        aggregate_id=income.id,
        action="expected_income_created",
        changed_fields=[
            "name",
            "expected_amount",
            "expected_date",
            "recurrence",
            "amount_is_variable",
        ],
    )
    session.commit()
    session.refresh(income)
    return income


@router.patch("/incomes/{income_id}", response_model=ExpectedIncomeRead)
def update_expected_income(
    income_id: UUID,
    request: ExpectedIncomePatch,
    session: DatabaseSession,
) -> ExpectedIncome:
    income = session.get(ExpectedIncome, income_id)
    if income is None or income.deleted_at is not None:
        raise _not_found("expected_income_not_found")
    fields = request.model_fields_set
    for field in fields:
        value = getattr(request, field)
        if field == "name" and value is not None:
            value = value.strip()
        if value is not None:
            setattr(income, field, value)
    if fields:
        _audit(
            session,
            aggregate_type="expected_income",
            aggregate_id=income.id,
            action="expected_income_updated",
            changed_fields=sorted(fields),
        )
        session.commit()
        session.refresh(income)
    return income


@router.delete("/incomes/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expected_income(income_id: UUID, session: DatabaseSession) -> None:
    income = session.get(ExpectedIncome, income_id)
    if income is None or income.deleted_at is not None:
        raise _not_found("expected_income_not_found")
    income.deleted_at = utc_now()
    _audit(
        session,
        aggregate_type="expected_income",
        aggregate_id=income.id,
        action="expected_income_soft_deleted",
        changed_fields=["deleted_at"],
    )
    session.commit()


@router.get("/expenses", response_model=list[PlannedExpenseRead])
def list_planned_expenses(
    session: DatabaseSession,
    include_cancelled: Annotated[bool, Query()] = False,
) -> list[PlannedExpense]:
    statement = select(PlannedExpense).where(PlannedExpense.deleted_at.is_(None))
    if not include_cancelled:
        statement = statement.where(PlannedExpense.status != PlannedExpenseStatus.CANCELLED)
    return list(session.scalars(statement.order_by(PlannedExpense.due_date, PlannedExpense.id)))


@router.post("/expenses", response_model=PlannedExpenseRead, status_code=status.HTTP_201_CREATED)
def create_planned_expense(
    request: PlannedExpenseCreate, session: DatabaseSession
) -> PlannedExpense:
    _validate_category(session, request.category_id)
    expense = PlannedExpense(
        name=request.name.strip(),
        expected_amount=request.expected_amount,
        due_date=request.due_date,
        recurrence=request.recurrence,
        amount_is_variable=request.amount_is_variable,
        category_id=request.category_id,
        status=PlannedExpenseStatus.PLANNED,
    )
    session.add(expense)
    session.flush()
    _audit(
        session,
        aggregate_type="planned_expense",
        aggregate_id=expense.id,
        action="planned_expense_created",
        changed_fields=[
            "name",
            "expected_amount",
            "due_date",
            "recurrence",
            "amount_is_variable",
            "category_id",
        ],
    )
    session.commit()
    session.refresh(expense)
    return expense


@router.patch("/expenses/{expense_id}", response_model=PlannedExpenseRead)
def update_planned_expense(
    expense_id: UUID,
    request: PlannedExpensePatch,
    session: DatabaseSession,
) -> PlannedExpense:
    expense = session.get(PlannedExpense, expense_id)
    if expense is None or expense.deleted_at is not None:
        raise _not_found("planned_expense_not_found")
    fields = request.model_fields_set
    if "category_id" in fields:
        _validate_category(session, request.category_id)
        expense.category_id = request.category_id
    for field in fields - {"category_id"}:
        value = getattr(request, field)
        if field == "name" and value is not None:
            value = value.strip()
        if value is not None:
            setattr(expense, field, value)
    if fields:
        _audit(
            session,
            aggregate_type="planned_expense",
            aggregate_id=expense.id,
            action="planned_expense_updated",
            changed_fields=sorted(fields),
        )
        session.commit()
        session.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planned_expense(expense_id: UUID, session: DatabaseSession) -> None:
    expense = session.get(PlannedExpense, expense_id)
    if expense is None or expense.deleted_at is not None:
        raise _not_found("planned_expense_not_found")
    expense.deleted_at = utc_now()
    _audit(
        session,
        aggregate_type="planned_expense",
        aggregate_id=expense.id,
        action="planned_expense_soft_deleted",
        changed_fields=["deleted_at"],
    )
    session.commit()


@router.get("/settings", response_model=BudgetSettingsRead)
def get_budget_settings(session: DatabaseSession) -> BudgetSettings:
    settings = default_budget_settings(session)
    session.commit()
    session.refresh(settings)
    return settings


@router.put("/settings", response_model=BudgetSettingsRead)
def update_budget_settings(
    request: BudgetSettingsUpdate, session: DatabaseSession
) -> BudgetSettings:
    settings = default_budget_settings(session)
    settings.minimum_reserve = request.minimum_reserve
    settings.include_pending_transactions = request.include_pending_transactions
    changed_fields = ["minimum_reserve", "include_pending_transactions"]
    if request.telegram_notifications_enabled is not None:
        settings.telegram_notifications_enabled = request.telegram_notifications_enabled
        changed_fields.append("telegram_notifications_enabled")
    _audit(
        session,
        aggregate_type="budget_settings",
        aggregate_id=settings.id,
        action="budget_settings_updated",
        changed_fields=changed_fields,
    )
    session.commit()
    session.refresh(settings)
    return settings
