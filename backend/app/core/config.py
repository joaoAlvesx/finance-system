from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINANCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Finance API"
    environment: str = "local"
    database_url: str = (
        "postgresql+psycopg://finance_app:local-development-only@localhost:5432/finance"
    )
    timezone: str = "America/Campo_Grande"
    log_level: str = "INFO"
    db_connect_attempts: int = Field(default=20, ge=1, le=120)
    db_connect_delay_seconds: float = Field(default=2, ge=0.1, le=30)
    csv_upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    telegram_enabled: bool = False
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_poll_seconds: int = Field(default=20, ge=1, le=50)
    telegram_scan_seconds: int = Field(default=15, ge=1, le=300)
    telegram_max_attempts: int = Field(default=3, ge=1, le=10)
    telegram_request_timeout_seconds: int = Field(default=30, ge=2, le=60)
    pluggy_enabled: bool = False
    pluggy_client_id: SecretStr = SecretStr("")
    pluggy_client_secret: SecretStr = SecretStr("")
    pluggy_api_base_url: str = "https://api.pluggy.ai"
    pluggy_client_user_id: str = "finance-system-personal"
    pluggy_connector_id: int = Field(default=200, ge=1)
    pluggy_include_sandbox: bool = True
    pluggy_poll_seconds: int = Field(default=900, ge=60, le=86400)
    pluggy_full_sync_seconds: int = Field(default=86400, ge=3600, le=604800)
    pluggy_worker_scan_seconds: int = Field(default=15, ge=1, le=300)
    pluggy_request_timeout_seconds: int = Field(default=30, ge=2, le=120)
    pluggy_max_attempts: int = Field(default=5, ge=1, le=10)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA name") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
