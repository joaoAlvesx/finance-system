import calendar
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.assistant import CategorySuggestion
from app.models.category import Category
from app.models.enums import (
    CategorySuggestionStatus,
    PlannedExpenseStatus,
    TransactionStatus,
    TransactionType,
)
from app.models.planning import PlannedExpense
from app.models.transaction import Transaction
from app.schemas.assistant import (
    AssistantTransaction,
    AvailabilityResult,
    BalanceResult,
    FutureExpenseListResult,
    FutureExpenseResult,
    InsightCard,
    InsightsResponse,
    MonthlyCategoryTotal,
    MonthlySummaryResult,
    NaturalLanguageResponse,
    PurchaseSimulationResult,
    TransactionListResult,
)
from app.services.dashboard import (
    account_balance_at_present,
    availability_values,
    consolidated_current_balance,
    default_budget_settings,
    local_today,
    next_expected_income,
)
from app.services.deduplication import normalize_description
from app.services.money import money
from app.services.projections import safe_daily_limit

MONEY_IN_QUESTION = re.compile(r"(?:r\$\s*)?(\d{1,9}(?:[.,]\d{1,2})?)", re.IGNORECASE)


def _brl(value: Decimal) -> str:
    whole, cents = f"{money(value):.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return f"R$ {'.'.join(reversed(groups))},{cents}"


def balance_result(
    session: Session, *, account_id: UUID | None = None
) -> BalanceResult:
    settings = default_budget_settings(session)
    if account_id is None:
        balance = consolidated_current_balance(session, timezone=settings.timezone)
    else:
        account = session.get(Account, account_id)
        if account is None or account.deleted_at is not None or not account.is_active:
            raise LookupError("account_not_found")
        balance = account_balance_at_present(session, account, timezone=settings.timezone)
    return BalanceResult(
        calculated_at=datetime.now(UTC), account_id=account_id, balance=balance
    )


def availability_result(session: Session) -> AvailabilityResult:
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    balance = consolidated_current_balance(session, timezone=settings.timezone)
    income = next_expected_income(session, today=today)
    available, daily, committed, deficit = availability_values(
        session,
        balance=balance,
        reserve=settings.minimum_reserve,
        today=today,
        income=income,
    )
    return AvailabilityResult(
        calculated_at=datetime.now(UTC),
        current_balance=balance,
        available_until_next_income=available,
        daily_safe_limit=daily,
        committed_expenses=committed,
        minimum_reserve=settings.minimum_reserve,
        deficit=deficit,
        next_income_date=income.expected_date if income else None,
        days_until_next_income=max(1, (income.expected_date - today).days) if income else None,
    )


def transaction_list(
    session: Session,
    *,
    date_from: date,
    date_to: date,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    search: str | None = None,
    limit: int = 25,
) -> TransactionListResult:
    statement = (
        select(Transaction, Category.name)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
    )
    if account_id:
        statement = statement.where(Transaction.account_id == account_id)
    if category_id:
        statement = statement.where(Transaction.category_id == category_id)
    if search:
        statement = statement.where(Transaction.description_raw.ilike(f"%{search.strip()}%"))
    rows = list(
        session.execute(
            statement.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(
                limit + 1
            )
        )
    )
    items = [
        AssistantTransaction(
            id=transaction.id,
            account_id=transaction.account_id,
            transaction_date=transaction.transaction_date,
            description=transaction.description_raw,
            amount=transaction.amount,
            direction=transaction.direction,
            type=transaction.type,
            status=transaction.status,
            category_id=transaction.category_id,
            category_name=category_name,
        )
        for transaction, category_name in rows[:limit]
    ]
    return TransactionListResult(items=items, count=len(items), limited=len(rows) > limit)


def future_expense_list(
    session: Session, *, start: date, end: date, limit: int = 25
) -> FutureExpenseListResult:
    rows = list(
        session.scalars(
            select(PlannedExpense)
            .where(
                PlannedExpense.deleted_at.is_(None),
                PlannedExpense.status.in_(
                    [PlannedExpenseStatus.PLANNED, PlannedExpenseStatus.LATE]
                ),
                PlannedExpense.due_date >= start,
                PlannedExpense.due_date <= end,
            )
            .order_by(PlannedExpense.due_date, PlannedExpense.id)
            .limit(limit + 1)
        )
    )
    items = [
        FutureExpenseResult(
            id=item.id,
            name=item.name,
            expected_amount=item.expected_amount,
            due_date=item.due_date,
            category_id=item.category_id,
            status=item.status.value,
        )
        for item in rows[:limit]
    ]
    return FutureExpenseListResult(items=items, count=len(items), limited=len(rows) > limit)


def monthly_summary(session: Session, *, year: int, month: int) -> MonthlySummaryResult:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    totals = session.execute(
        select(Transaction.type, func.sum(Transaction.amount))
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type != TransactionType.TRANSFER,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .group_by(Transaction.type)
    )
    values = {kind: money(amount) for kind, amount in totals}
    income = values.get(TransactionType.INCOME, Decimal("0.00"))
    expense = values.get(TransactionType.EXPENSE, Decimal("0.00"))
    categories = session.execute(
        select(
            Transaction.category_id,
            func.coalesce(Category.name, "Sem categoria"),
            func.sum(Transaction.amount),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .group_by(Transaction.category_id, Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(12)
    )
    return MonthlySummaryResult(
        year=year,
        month=month,
        income=income,
        expense=expense,
        net=money(income - expense),
        by_category=[
            MonthlyCategoryTotal(category_id=category_id, category_name=name, amount=money(amount))
            for category_id, name, amount in categories
        ],
    )


def purchase_simulation(session: Session, *, amount: Decimal) -> PurchaseSimulationResult:
    current = availability_result(session)
    balance_after = money(current.current_balance - amount)
    if current.available_until_next_income is None:
        available_after = None
        daily_after = None
        deficit_after = Decimal("0.00")
    else:
        raw_available = money(current.available_until_next_income - amount)
        available_after = max(Decimal("0.00"), raw_available)
        deficit_after = max(Decimal("0.00"), -raw_available)
        settings = default_budget_settings(session)
        today = local_today(settings.timezone)
        daily_after = safe_daily_limit(
            available_after, today=today, next_income_date=current.next_income_date
        )
    return PurchaseSimulationResult(
        amount=amount,
        balance_after_purchase=balance_after,
        available_after_purchase=available_after,
        daily_safe_limit_after_purchase=daily_after,
        deficit_after_purchase=deficit_after,
        next_income_date=current.next_income_date,
    )


def natural_language_answer(session: Session, question: str) -> NaturalLanguageResponse:
    normalized = normalize_description(question)
    if "simul" in normalized or "se eu gastar" in normalized:
        match = MONEY_IN_QUESTION.search(normalized)
        if match is None:
            return NaturalLanguageResponse(
                intent="simulation_missing_amount",
                value_kind="suggestion",
                answer="Informe o valor da compra, por exemplo: simule um gasto de R$ 80,00.",
            )
        amount = money(match.group(1).replace(",", "."))
        if amount <= 0:
            return NaturalLanguageResponse(
                intent="simulation_invalid_amount",
                value_kind="suggestion",
                answer="O valor da simulação precisa ser maior que zero.",
            )
        result = purchase_simulation(session, amount=amount)
        available = (
            _brl(result.available_after_purchase)
            if result.available_after_purchase is not None
            else "indisponível sem uma próxima entrada cadastrada"
        )
        return NaturalLanguageResponse(
            intent="simulate_purchase",
            value_kind="prediction",
            answer=f"Após um gasto de {_brl(amount)}, o disponível seria {available}.",
            data=result.model_dump(mode="json"),
        )
    if "dispon" in normalized or "limite" in normalized:
        result = availability_result(session)
        if result.available_until_next_income is None:
            answer = "Cadastre uma próxima entrada para calcular o disponível e o limite diário."
        else:
            answer = (
                f"Você tem {_brl(result.available_until_next_income)} disponíveis até a próxima "
                f"entrada e limite diário de {_brl(result.daily_safe_limit or Decimal('0.00'))}."
            )
        return NaturalLanguageResponse(
            intent="availability",
            value_kind="calculated",
            answer=answer,
            data=result.model_dump(mode="json"),
        )
    if "resumo" in normalized or "mes" in normalized:
        settings = default_budget_settings(session)
        today = local_today(settings.timezone)
        result = monthly_summary(session, year=today.year, month=today.month)
        return NaturalLanguageResponse(
            intent="monthly_summary",
            value_kind="calculated",
            answer=(
                f"Neste mês entraram {_brl(result.income)} e saíram {_brl(result.expense)}; "
                f"o resultado é {_brl(result.net)}."
            ),
            data=result.model_dump(mode="json"),
        )
    if "conta" in normalized and any(word in normalized for word in ("futura", "proxima", "vence")):
        settings = default_budget_settings(session)
        today = local_today(settings.timezone)
        result = future_expense_list(session, start=today, end=today + timedelta(days=45))
        return NaturalLanguageResponse(
            intent="future_expenses",
            value_kind="calculated",
            answer=f"Há {result.count} conta(s) planejada(s) nos próximos 45 dias.",
            data=result.model_dump(mode="json"),
        )
    if "saldo" in normalized:
        result = balance_result(session)
        return NaturalLanguageResponse(
            intent="balance",
            value_kind="calculated",
            answer=f"O saldo consolidado calculado é {_brl(result.balance)}.",
            data=result.model_dump(mode="json"),
        )
    return NaturalLanguageResponse(
        intent="help",
        value_kind="suggestion",
        answer=(
            "Posso consultar saldo, disponível, contas futuras e resumo mensal, "
            "ou simular uma compra."
        ),
    )


def insight_cards(session: Session) -> InsightsResponse:
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    availability = availability_result(session)
    cards: list[InsightCard] = []
    if availability.available_until_next_income is None:
        cards.append(
            InsightCard(
                key="projection",
                title="Projeção pendente",
                text="Cadastre a próxima entrada para calcular o disponível e o limite diário.",
                value_kind="suggestion",
                severity="attention",
            )
        )
    else:
        cards.append(
            InsightCard(
                key="projection",
                title="Até a próxima entrada",
                text=(
                    f"Disponível {_brl(availability.available_until_next_income)}; "
                    f"limite diário {_brl(availability.daily_safe_limit or Decimal('0.00'))}."
                ),
                value_kind="prediction",
            )
        )

    month_start = today.replace(day=1)
    previous_end = month_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    category_rows = session.execute(
        select(Category.name, Transaction.transaction_date, Transaction.amount)
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.transaction_date >= previous_start,
            Transaction.transaction_date <= today,
        )
    )
    category_values: dict[str, list[Decimal]] = defaultdict(
        lambda: [Decimal("0.00"), Decimal("0.00")]
    )
    for name, transaction_date, amount in category_rows:
        category_values[name][0 if transaction_date >= month_start else 1] += amount
    growth = [
        (money((current - previous) / previous * 100), name, current, previous)
        for name, (current, previous) in category_values.items()
        if previous > 0 and current > previous
    ]
    if growth:
        percent, name, current, _ = max(growth)
        cards.append(
            InsightCard(
                key="category_growth",
                title="Categoria em alta",
                text=f"{name} subiu {percent:.0f}% neste mês e soma {_brl(current)}.",
                value_kind="calculated",
                severity="attention",
            )
        )

    review_count = session.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.deleted_at.is_(None),
            Transaction.category_id.is_(None),
        )
    ) or 0
    pending_suggestions = session.scalar(
        select(func.count(CategorySuggestion.id)).where(
            CategorySuggestion.deleted_at.is_(None),
            CategorySuggestion.status == CategorySuggestionStatus.PENDING,
        )
    ) or 0
    cards.append(
        InsightCard(
            key="category_review",
            title="Categorias pendentes",
            text=(
                f"{review_count} transação(ões) sem categoria e "
                f"{pending_suggestions} sugestão(ões)."
            ),
            value_kind="calculated",
            severity="attention" if review_count else "neutral",
        )
    )

    duplicate_groups = session.scalar(
        select(func.count())
        .select_from(
            select(Transaction.deduplication_hash)
            .where(Transaction.deleted_at.is_(None))
            .group_by(Transaction.deduplication_hash)
            .having(func.count(Transaction.id) > 1)
            .subquery()
        )
    ) or 0
    cards.append(
        InsightCard(
            key="duplicates",
            title="Possíveis duplicidades",
            text=f"{duplicate_groups} grupo(s) com lançamentos iguais para revisar.",
            value_kind="suggestion",
            severity="attention" if duplicate_groups else "neutral",
        )
    )

    since = today - timedelta(days=90)
    recurring_rows = session.execute(
        select(
            Transaction.description_normalized,
            func.count(Transaction.id),
            func.sum(Transaction.amount),
        )
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.status != TransactionStatus.IGNORED,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.transaction_date >= since,
        )
        .group_by(Transaction.description_normalized)
        .having(func.count(Transaction.id) >= 2)
        .order_by(func.count(Transaction.id).desc())
        .limit(1)
    ).first()
    if recurring_rows:
        description, count, total = recurring_rows
        cards.append(
            InsightCard(
                key="recurring",
                title="Despesa recorrente possível",
                text=f"{description[:80]} apareceu {count} vezes e soma {_brl(total)} em 90 dias.",
                value_kind="suggestion",
            )
        )
    return InsightsResponse(
        generated_at=datetime.now(UTC),
        cards=cards,
        suggested_questions=[
            "Qual é meu saldo?",
            "Quanto posso gastar até a próxima entrada?",
            "Mostre meu resumo do mês",
            "Simule um gasto de R$ 100,00",
        ],
    )
