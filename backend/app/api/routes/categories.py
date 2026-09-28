from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.models.account import Account
from app.models.audit import AuditEvent
from app.models.category import Category, CategoryRule
from app.models.enums import AuditActorType, RuleOrigin
from app.schemas.categories import (
    CategoryCreate,
    CategoryRead,
    CategoryRuleCreate,
    CategoryRuleRead,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(session: DatabaseSession) -> list[Category]:
    return list(
        session.scalars(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        )
    )


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(request: CategoryCreate, session: DatabaseSession) -> Category:
    if request.parent_id and session.get(Category, request.parent_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "parent_category_not_found",
                "message": "Parent category was not found",
            },
        )
    normalized_name = request.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "category_name_empty", "message": "Category name cannot be empty"},
        )
    if session.scalar(
        select(Category.id).where(func.lower(Category.name) == normalized_name.casefold())
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "category_name_exists", "message": "Category name already exists"},
        )
    category = Category(
        name=normalized_name,
        parent_id=request.parent_id,
        color=request.color,
        icon=request.icon,
        kind=request.kind,
        is_active=True,
    )
    try:
        session.add(category)
        session.flush()
        session.add(
            AuditEvent(
                aggregate_type="category",
                aggregate_id=category.id,
                action="category_created",
                changed_fields=["name", "parent_id", "color", "icon", "kind"],
                actor_type=AuditActorType.USER,
                actor_identifier="local-user",
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "category_name_exists", "message": "Category name already exists"},
        ) from exc
    session.refresh(category)
    return category


@router.get("/rules", response_model=list[CategoryRuleRead])
def list_rules(session: DatabaseSession) -> list[CategoryRule]:
    return list(
        session.scalars(
            select(CategoryRule)
            .where(CategoryRule.is_active.is_(True))
            .order_by(CategoryRule.priority.desc(), CategoryRule.id)
        )
    )


@router.post("/rules", response_model=CategoryRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(request: CategoryRuleCreate, session: DatabaseSession) -> CategoryRule:
    category = session.get(Category, request.category_id)
    if category is None or not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "category_not_found", "message": "Category was not found"},
        )
    if request.account_id:
        account = session.get(Account, request.account_id)
        if account is None or account.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "account_not_found", "message": "Account was not found"},
            )
    rule = CategoryRule(
        match_field=request.match_field,
        pattern=request.pattern.strip(),
        category_id=request.category_id,
        priority=request.priority,
        account_id=request.account_id,
        hit_count=0,
        origin=RuleOrigin.MANUAL,
        is_active=True,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule
