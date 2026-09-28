import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramAPIError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TelegramUpdate:
    update_id: int
    chat_id: str
    text: str


class TelegramGateway(Protocol):
    def send_message(self, *, chat_id: str, text: str) -> str: ...

    def get_updates(self, *, offset: int | None, timeout: int) -> list[TelegramUpdate]: ...


class TelegramBotClient:
    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.telegram.org",
        request_timeout: int = 30,
    ) -> None:
        if not token.strip():
            raise ValueError("telegram token is required")
        self._endpoint = f"{base_url.rstrip('/')}/bot{token.strip()}"
        self._request_timeout = request_timeout

    def _call(self, method: str, payload: dict[str, object]) -> object:
        request = Request(
            f"{self._endpoint}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._request_timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise TelegramAPIError(f"telegram_http_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise TelegramAPIError("telegram_unavailable") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise TelegramAPIError("telegram_invalid_response") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            error_code = result.get("error_code") if isinstance(result, dict) else None
            safe_code = error_code if isinstance(error_code, int) else "unknown"
            raise TelegramAPIError(f"telegram_api_{safe_code}")
        return result.get("result")

    def send_message(self, *, chat_id: str, text: str) -> str:
        result = self._call("sendMessage", {"chat_id": chat_id, "text": text})
        if not isinstance(result, dict):
            raise TelegramAPIError("telegram_invalid_message")
        message_id = result.get("message_id")
        if not isinstance(message_id, int):
            raise TelegramAPIError("telegram_invalid_message")
        return str(message_id)

    def get_updates(self, *, offset: int | None, timeout: int) -> list[TelegramUpdate]:
        payload: dict[str, object] = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload)
        if not isinstance(result, list):
            raise TelegramAPIError("telegram_invalid_updates")
        updates: list[TelegramUpdate] = []
        for item in result:
            if not isinstance(item, dict) or not isinstance(item.get("update_id"), int):
                continue
            message = item.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("text"), str):
                continue
            chat = message.get("chat")
            if not isinstance(chat, dict) or not isinstance(chat.get("id"), int | str):
                continue
            updates.append(
                TelegramUpdate(
                    update_id=item["update_id"],
                    chat_id=str(chat["id"]),
                    text=message["text"],
                )
            )
        return updates
