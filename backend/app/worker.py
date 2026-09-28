import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.integrations.pluggy import PluggyClient
from app.integrations.telegram import TelegramAPIError, TelegramBotClient
from app.models.enums import SyncRunStatus
from app.services.pluggy_sync import process_next_pluggy_job
from app.services.telegram_notifications import (
    dispatch_notifications,
    process_telegram_updates,
    scan_new_expenses,
)

logger = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, use_json=settings.environment == "production")
    telegram_client: TelegramBotClient | None = None
    pluggy_client: PluggyClient | None = None
    chat_id = ""
    if settings.telegram_enabled:
        token = settings.telegram_bot_token.get_secret_value().strip()
        chat_id = settings.telegram_chat_id.strip()
        if not token or not chat_id:
            raise RuntimeError("telegram worker requires token and chat id")
        telegram_client = TelegramBotClient(
            token=token,
            base_url=settings.telegram_api_base_url,
            request_timeout=settings.telegram_request_timeout_seconds,
        )
        logger.info("telegram worker started")
    else:
        logger.info("telegram worker is disabled")

    if settings.pluggy_enabled:
        client_id = settings.pluggy_client_id.get_secret_value().strip()
        client_secret = settings.pluggy_client_secret.get_secret_value().strip()
        if not client_id or not client_secret:
            raise RuntimeError("pluggy worker requires client id and client secret")
        pluggy_client = PluggyClient(
            client_id=client_id,
            client_secret=client_secret,
            base_url=settings.pluggy_api_base_url,
            request_timeout=settings.pluggy_request_timeout_seconds,
        )
        logger.info("pluggy worker started")
    else:
        logger.info("pluggy worker is disabled")

    if telegram_client is None and pluggy_client is None:
        while True:
            time.sleep(3600)

    next_pluggy_scan = 0.0
    while True:
        if pluggy_client is not None and time.monotonic() >= next_pluggy_scan:
            try:
                with SessionLocal() as session:
                    sync_run = process_next_pluggy_job(
                        session,
                        pluggy_client,
                        timezone=settings.timezone,
                        poll_seconds=settings.pluggy_poll_seconds,
                        full_sync_seconds=settings.pluggy_full_sync_seconds,
                        max_attempts=settings.pluggy_max_attempts,
                    )
                if sync_run is not None:
                    logger.info(
                        "pluggy sync completed status=%s created=%d updated=%d "
                        "reconciled=%d ignored=%d",
                        sync_run.status.value,
                        sync_run.created_count,
                        sync_run.updated_count,
                        sync_run.reconciled_count,
                        sync_run.ignored_count,
                    )
                    if sync_run.status == SyncRunStatus.FAILED:
                        logger.warning("pluggy sync failed code=%s", sync_run.error_code)
            except Exception:
                logger.warning("pluggy worker cycle failed; retrying")
            next_pluggy_scan = time.monotonic() + settings.pluggy_worker_scan_seconds

        if telegram_client is not None:
            try:
                with SessionLocal() as session:
                    queued = scan_new_expenses(session)
                    sent, failed = dispatch_notifications(
                        session,
                        telegram_client,
                        chat_id=chat_id,
                        max_attempts=settings.telegram_max_attempts,
                    )
                if queued or sent or failed:
                    logger.info(
                        "telegram notification cycle completed queued=%d sent=%d failed=%d",
                        queued,
                        sent,
                        failed,
                    )
                with SessionLocal() as session:
                    answered, ignored = process_telegram_updates(
                        session,
                        telegram_client,
                        allowed_chat_id=chat_id,
                        timeout=settings.telegram_poll_seconds,
                    )
                if answered or ignored:
                    logger.info(
                        "telegram update cycle completed answered=%d ignored=%d",
                        answered,
                        ignored,
                    )
            except TelegramAPIError as exc:
                logger.warning("telegram API request failed code=%s", exc.code)
                time.sleep(settings.telegram_scan_seconds)
            except Exception:
                logger.warning("telegram worker cycle failed; retrying")
                time.sleep(settings.telegram_scan_seconds)
        else:
            time.sleep(settings.pluggy_worker_scan_seconds)


if __name__ == "__main__":
    run()
