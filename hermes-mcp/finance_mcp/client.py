import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class FinanceAPIError(RuntimeError):
    pass


class FinanceAPIClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("FINANCE_API_URL", "")).rstrip("/")
        self.token = token or os.environ.get("FINANCE_API_TOKEN", "")
        if not self.base_url or not self.token:
            raise RuntimeError("FINANCE_API_URL and FINANCE_API_TOKEN are required")

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str | int | None] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/assistant/tools{path}"
        filtered_query = {key: value for key, value in (query or {}).items() if value is not None}
        if filtered_query:
            url = f"{url}?{urllib.parse.urlencode(filtered_query)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "finance-hermes-mcp/0.6.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.load(exc)
                code = payload.get("detail", {}).get("code", "finance_api_error")
            except (ValueError, AttributeError):
                code = "finance_api_error"
            raise FinanceAPIError(f"Finance API rejected the request: {code}") from exc
        except urllib.error.URLError as exc:
            raise FinanceAPIError("Finance API is unavailable") from exc
