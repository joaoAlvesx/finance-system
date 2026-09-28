import json
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from app.integrations.pluggy.types import (
    ExternalAccount,
    ExternalItem,
    ExternalTransaction,
    TransactionPage,
)


class PluggyAPIError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code[:120]
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal | int | str):
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        return parsed if parsed.is_finite() else None
    return None


def _safe_error_code(payload: object, status_code: int) -> str:
    if isinstance(payload, dict):
        for key in ("code", "codeDescription", "errorCode"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                cleaned = "".join(char for char in value if char.isalnum() or char in "_-.")
                if cleaned:
                    return f"pluggy_{cleaned.lower()}"[:120]
    return f"pluggy_http_{status_code}"


class PluggyClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str = "https://api.pluggy.ai",
        request_timeout: int = 30,
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("pluggy credentials are required")
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._base_url = base_url.rstrip("/")
        self._request_timeout = request_timeout
        self._api_key = ""
        self._api_key_expires_at = 0.0

    def _decode(self, raw: bytes) -> object:
        try:
            return json.loads(raw.decode("utf-8"), parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise PluggyAPIError("pluggy_invalid_response") from None

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        authenticated: bool = True,
    ) -> object:
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["X-API-KEY"] = self._get_api_key()
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._request_timeout) as response:
                return self._decode(response.read())
        except HTTPError as exc:
            try:
                error_payload = self._decode(exc.read())
            except PluggyAPIError:
                error_payload = None
            retry_after = exc.headers.get("Retry-After")
            retry_after_seconds = (
                int(retry_after) if retry_after and retry_after.isdigit() else None
            )
            raise PluggyAPIError(
                _safe_error_code(error_payload, exc.code),
                retryable=exc.code in {408, 409, 425, 429, 500, 502, 503, 504},
                retry_after_seconds=retry_after_seconds,
            ) from None
        except (URLError, TimeoutError, OSError):
            raise PluggyAPIError("pluggy_unavailable", retryable=True) from None

    def _get_api_key(self) -> str:
        if self._api_key and time.monotonic() < self._api_key_expires_at:
            return self._api_key
        result = self._request(
            "POST",
            "/auth",
            payload={"clientId": self._client_id, "clientSecret": self._client_secret},
            authenticated=False,
        )
        token = result.get("apiKey") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            token = result.get("accessToken") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise PluggyAPIError("pluggy_invalid_auth_response")
        self._api_key = token
        self._api_key_expires_at = time.monotonic() + 6900
        return token

    def create_connect_token(self, *, client_user_id: str, item_id: str | None = None) -> str:
        payload: dict[str, object] = {
            "options": {"clientUserId": client_user_id, "avoidDuplicates": True}
        }
        if item_id:
            payload["itemId"] = item_id
        result = self._request("POST", "/connect_token", payload=payload)
        token = result.get("accessToken") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            token = result.get("connectToken") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise PluggyAPIError("pluggy_invalid_connect_token_response")
        return token

    def get_item(self, item_id: str) -> ExternalItem:
        result = self._request("GET", f"/items/{item_id}")
        if not isinstance(result, dict):
            raise PluggyAPIError("pluggy_invalid_item_response")
        connector = result.get("connector")
        connector_id = connector.get("id") if isinstance(connector, dict) else None
        connector_name = connector.get("name") if isinstance(connector, dict) else None
        error = result.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        consent = (
            result.get("consentExpiresAt")
            or result.get("consentExpirationDate")
            or result.get("expirationDate")
        )
        return ExternalItem(
            id=str(result.get("id") or item_id),
            connector_id=connector_id if isinstance(connector_id, int) else None,
            connector_name=connector_name if isinstance(connector_name, str) else None,
            status=str(result.get("status") or "UNKNOWN").upper(),
            execution_status=(
                str(result["executionStatus"]).upper()
                if result.get("executionStatus") is not None
                else None
            ),
            error_code=str(error_code)[:120] if isinstance(error_code, str) else None,
            consent_expires_at=_datetime(consent),
            updated_at=_datetime(result.get("lastUpdatedAt")),
        )

    def trigger_item_update(self, item_id: str) -> None:
        self._request("PATCH", f"/items/{item_id}", payload={})

    def list_accounts(self, item_id: str) -> list[ExternalAccount]:
        result = self._request("GET", f"/accounts?{urlencode({'itemId': item_id})}")
        rows = result.get("results") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            raise PluggyAPIError("pluggy_invalid_accounts_response")
        accounts: list[ExternalAccount] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            currency = str(row.get("currencyCode") or "BRL").upper()
            accounts.append(
                ExternalAccount(
                    id=row["id"],
                    item_id=str(row.get("itemId") or item_id),
                    name=str(row.get("name") or row.get("marketingName") or "Conta Pluggy")[:160],
                    type=str(row.get("type") or "BANK").upper(),
                    subtype=str(row["subtype"]).upper() if row.get("subtype") else None,
                    currency_code=currency[:3],
                    balance=_decimal(row.get("balance")),
                )
            )
        return accounts

    def list_transactions(
        self,
        account_id: str,
        *,
        cursor: str | None = None,
        created_at_from: datetime | None = None,
    ) -> TransactionPage:
        if cursor:
            parsed = urlsplit(cursor)
            query = parse_qs(parsed.query if parsed.query else cursor.removeprefix("?"))
            if query.get("accountId", [account_id])[0] != account_id:
                raise PluggyAPIError("pluggy_invalid_cursor")
            path = f"/v2/transactions?{urlencode(query, doseq=True)}"
        else:
            query_values: dict[str, str] = {"accountId": account_id}
            if created_at_from is not None:
                query_values["createdAtFrom"] = (
                    created_at_from.astimezone(UTC)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
            path = f"/v2/transactions?{urlencode(query_values)}"
        result = self._request("GET", path)
        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise PluggyAPIError("pluggy_invalid_transactions_response")
        transactions: list[ExternalTransaction] = []
        for row in result["results"]:
            transaction = self._transaction(row, account_id)
            if transaction is not None:
                transactions.append(transaction)
        next_cursor = result.get("next")
        return TransactionPage(
            transactions=transactions,
            next_cursor=next_cursor if isinstance(next_cursor, str) and next_cursor else None,
        )

    def _transaction(self, row: object, account_id: str) -> ExternalTransaction | None:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            return None
        amount = _decimal(row.get("amount"))
        posted_at = _datetime(row.get("date"))
        if amount is None or posted_at is None:
            return None
        merchant = row.get("merchant")
        merchant_name = merchant.get("name") if isinstance(merchant, dict) else None
        return ExternalTransaction(
            id=row["id"],
            account_id=str(row.get("accountId") or account_id),
            description=str(row.get("description") or row.get("descriptionRaw") or "Transação")[
                :1000
            ],
            description_raw=(
                str(row["descriptionRaw"])[:1000] if row.get("descriptionRaw") else None
            ),
            amount=amount,
            currency_code=str(row.get("currencyCode") or "BRL").upper()[:3],
            date=posted_at,
            type=str(row["type"]).upper() if row.get("type") else None,
            status=str(row.get("status") or "POSTED").upper(),
            merchant_name=str(merchant_name)[:255] if isinstance(merchant_name, str) else None,
            provider_category=(
                str(row["category"])[:120] if isinstance(row.get("category"), str) else None
            ),
        )
