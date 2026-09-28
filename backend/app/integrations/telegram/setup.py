from getpass import getpass

from app.core.config import get_settings
from app.integrations.telegram import TelegramAPIError, TelegramBotClient


def main() -> None:
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value().strip()
    if not token:
        token = getpass("Token do bot (não será exibido): ").strip()
    if not token:
        raise SystemExit("Token não informado.")
    client = TelegramBotClient(
        token=token,
        base_url=settings.telegram_api_base_url,
        request_timeout=settings.telegram_request_timeout_seconds,
    )
    try:
        updates = client.get_updates(offset=None, timeout=0)
    except TelegramAPIError as exc:
        raise SystemExit(f"Falha segura ao consultar o Telegram: {exc.code}") from None
    chat_ids = sorted({update.chat_id for update in updates})
    if not chat_ids:
        raise SystemExit("Nenhuma conversa encontrada. Envie /start ao bot e tente novamente.")
    print("Chat IDs encontrados após as mensagens recentes:")
    for chat_id in chat_ids:
        print(chat_id)


if __name__ == "__main__":
    main()
