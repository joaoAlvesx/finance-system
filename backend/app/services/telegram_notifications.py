import hmac
import re
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.integrations.telegram import TelegramAPIError, TelegramGateway
from app.models.category import Category
from app.models.enums import NotificationStatus, TransactionStatus, TransactionType
from app.models.integration import IntegrationCheckpoint, NotificationLog
from app.models.transaction import Transaction
from app.services.dashboard import (
    availability_values,
    consolidated_current_balance,
    default_budget_settings,
    local_today,
    next_expected_income,
)
from app.services.deduplication import recipient_label

CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")
EXPENSE_STREAM = "expense_alerts"
UPDATES_STREAM = "bot_updates"


def sanitize_telegram_text(value: str, *, limit: int = 100) -> str:
    cleaned = CONTROL_CHARACTERS.sub(" ", value)
    return " ".join(cleaned.split())[:limit]


def format_brl(value: Decimal) -> str:
    whole, decimal = f"{value:,.2f}".split(".")
    return f"R$ {whole.replace(',', '.')},{decimal}"


def _checkpoint(session: Session, stream: str) -> IntegrationCheckpoint | None:
    return session.scalar(
        select(IntegrationCheckpoint).where(
            IntegrationCheckpoint.integration == "telegram",
            IntegrationCheckpoint.stream == stream,
        )
    )


def initialize_expense_checkpoint(session: Session) -> IntegrationCheckpoint:
    checkpoint = _checkpoint(session, EXPENSE_STREAM)
    if checkpoint is not None:
        return checkpoint
    latest = session.execute(
        select(Transaction.created_at, Transaction.id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(1)
    ).one_or_none()
    cursor: dict[str, object] = {}
    if latest is not None:
        cursor = {"created_at": latest.created_at.isoformat(), "id": str(latest.id)}
    checkpoint = IntegrationCheckpoint(
        integration="telegram",
        stream=EXPENSE_STREAM,
        cursor=cursor,
        observed_at=utc_now(),
    )
    session.add(checkpoint)
    session.commit()
    session.refresh(checkpoint)
    return checkpoint


def scan_new_expenses(session: Session, *, batch_size: int = 200) -> int:
    checkpoint = _checkpoint(session, EXPENSE_STREAM)
    if checkpoint is None:
        initialize_expense_checkpoint(session)
        return 0

    statement = (
        select(Transaction).order_by(Transaction.created_at, Transaction.id).limit(batch_size)
    )
    cursor_created_at = checkpoint.cursor.get("created_at")
    cursor_id = checkpoint.cursor.get("id")
    if isinstance(cursor_created_at, str) and isinstance(cursor_id, str):
        created_at = datetime.fromisoformat(cursor_created_at)
        transaction_id = UUID(cursor_id)
        statement = statement.where(
            or_(
                Transaction.created_at > created_at,
                and_(Transaction.created_at == created_at, Transaction.id > transaction_id),
            )
        )

    settings = default_budget_settings(session)
    queued = 0
    rows = list(session.scalars(statement))
    for transaction in rows:
        if (
            settings.telegram_notifications_enabled
            and transaction.deleted_at is None
            and transaction.type == TransactionType.EXPENSE
            and transaction.status == TransactionStatus.POSTED
        ):
            idempotency_key = f"telegram:expense:{transaction.id}"
            exists = session.scalar(
                select(NotificationLog.id).where(NotificationLog.idempotency_key == idempotency_key)
            )
            if exists is None:
                session.add(
                    NotificationLog(
                        idempotency_key=idempotency_key,
                        notification_type="new_expense",
                        transaction_id=transaction.id,
                        status=NotificationStatus.PENDING,
                        attempt_count=0,
                        next_attempt_at=utc_now(),
                    )
                )
                queued += 1
        checkpoint.cursor = {
            "created_at": transaction.created_at.isoformat(),
            "id": str(transaction.id),
        }
        checkpoint.observed_at = utc_now()
    session.commit()
    return queued


def _availability(session: Session) -> tuple[Decimal, Decimal | None, Decimal | None, str]:
    settings = default_budget_settings(session)
    today = local_today(settings.timezone)
    balance = consolidated_current_balance(session, timezone=settings.timezone)
    income = next_expected_income(session, today=today)
    available, daily, _, _ = availability_values(
        session,
        balance=balance,
        reserve=settings.minimum_reserve,
        today=today,
        income=income,
    )
    return balance, available, daily, settings.timezone


def build_expense_alert(session: Session, transaction: Transaction) -> str:
    _, available, daily, timezone = _availability(session)
    category_name = "Sem categoria"
    if transaction.category_id:
        category = session.get(Category, transaction.category_id)
        if category is not None:
            category_name = sanitize_telegram_text(category.name, limit=60)
    merchant = sanitize_telegram_text(recipient_label(transaction.description_raw), limit=80)
    local_time = transaction.created_at.astimezone(ZoneInfo(timezone)).strftime("%d/%m/%Y %H:%M")
    available_text = format_brl(available) if available is not None else "não calculado"
    daily_text = format_brl(daily) if daily is not None else "não calculado"
    return "\n".join(
        [
            "💸 Novo gasto identificado",
            f"{format_brl(transaction.amount)} — {merchant or 'Descrição indisponível'}",
            f"Categoria: {category_name}",
            "",
            f"Disponível até a próxima entrada: {available_text}",
            f"Limite seguro diário: {daily_text}",
            f"Registrado em: {local_time}",
        ]
    )


def dispatch_notifications(
    session: Session,
    gateway: TelegramGateway,
    *,
    chat_id: str,
    max_attempts: int,
    limit: int = 20,
) -> tuple[int, int]:
    settings = default_budget_settings(session)
    if not settings.telegram_notifications_enabled:
        session.commit()
        return 0, 0
    now = utc_now()
    logs = list(
        session.scalars(
            select(NotificationLog)
            .where(
                NotificationLog.status.in_([NotificationStatus.PENDING, NotificationStatus.FAILED]),
                NotificationLog.attempt_count < max_attempts,
                or_(
                    NotificationLog.next_attempt_at.is_(None),
                    NotificationLog.next_attempt_at <= now,
                ),
            )
            .order_by(NotificationLog.created_at, NotificationLog.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    sent = 0
    failed = 0
    for log in logs:
        transaction = session.get(Transaction, log.transaction_id) if log.transaction_id else None
        if transaction is None or transaction.deleted_at is not None:
            log.status = NotificationStatus.FAILED
            log.attempt_count = max_attempts
            log.next_attempt_at = None
            log.error_code = "transaction_unavailable"
            failed += 1
            continue
        try:
            message_id = gateway.send_message(
                chat_id=chat_id,
                text=build_expense_alert(session, transaction),
            )
        except TelegramAPIError as exc:
            log.status = NotificationStatus.FAILED
            log.attempt_count += 1
            log.error_code = exc.code[:120]
            log.next_attempt_at = (
                now + timedelta(seconds=30 * (2 ** (log.attempt_count - 1)))
                if log.attempt_count < max_attempts
                else None
            )
            failed += 1
        else:
            log.status = NotificationStatus.SENT
            log.attempt_count += 1
            log.error_code = None
            log.next_attempt_at = None
            log.sent_at = utc_now()
            log.external_message_id = message_id[:120]
            sent += 1
        session.commit()
    return sent, failed


def command_reply(session: Session, text: str) -> str:
    command = text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0].casefold()
    balance, available, daily, _ = _availability(session)
    if command == "/saldo":
        return f"Saldo atual consolidado: {format_brl(balance)}"
    if command == "/disponivel":
        if available is None:
            return "Cadastre a próxima entrada para calcular o disponível."
        return "\n".join(
            [
                f"Disponível até a próxima entrada: {format_brl(available)}",
                f"Limite seguro diário: {format_brl(daily or Decimal('0.00'))}",
            ]
        )
    return "Comandos disponíveis:\n/saldo — saldo atual\n/disponivel — limite até a próxima entrada"


def process_telegram_updates(
    session: Session,
    gateway: TelegramGateway,
    *,
    allowed_chat_id: str,
    timeout: int,
) -> tuple[int, int]:
    checkpoint = _checkpoint(session, UPDATES_STREAM)
    if checkpoint is None:
        checkpoint = IntegrationCheckpoint(
            integration="telegram",
            stream=UPDATES_STREAM,
            cursor={},
            observed_at=utc_now(),
        )
        session.add(checkpoint)
        session.commit()
    last_update_id = checkpoint.cursor.get("update_id")
    offset = last_update_id + 1 if isinstance(last_update_id, int) else None
    updates = gateway.get_updates(offset=offset, timeout=timeout)
    answered = 0
    ignored = 0
    for update in sorted(updates, key=lambda item: item.update_id):
        if hmac.compare_digest(update.chat_id, allowed_chat_id):
            reply = command_reply(session, sanitize_telegram_text(update.text, limit=200))
            gateway.send_message(chat_id=allowed_chat_id, text=reply)
            answered += 1
        else:
            ignored += 1
        checkpoint.cursor = {"update_id": update.update_id}
        checkpoint.observed_at = utc_now()
        session.commit()
    return answered, ignored
