import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def wait_for_database() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, use_json=settings.environment == "production")
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    for attempt in range(1, settings.db_connect_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("database is ready")
            return
        except SQLAlchemyError:
            if attempt == settings.db_connect_attempts:
                logger.exception("database unavailable after %d attempts", attempt)
                raise
            logger.warning(
                "database unavailable; retrying (%d/%d)",
                attempt,
                settings.db_connect_attempts,
            )
            time.sleep(settings.db_connect_delay_seconds)
        finally:
            engine.dispose()


if __name__ == "__main__":
    wait_for_database()
