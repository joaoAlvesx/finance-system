import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.integrations.pluggy import PluggyClient


def test_pluggy_client_authenticates_and_uses_cursor_pagination() -> None:
    requests: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _payload(self) -> dict[str, object] | None:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length)) if length else None

        def do_POST(self) -> None:
            payload = self._payload()
            requests.append(("POST", self.path, payload, self.headers.get("X-API-KEY")))
            if self.path == "/auth":
                self._respond({"apiKey": "temporary-api-key"})
            else:
                self._respond({"accessToken": "short-lived-connect-token"})

        def do_GET(self) -> None:
            requests.append(("GET", self.path, None, self.headers.get("X-API-KEY")))
            if self.path.startswith("/items/"):
                self._respond(
                    {
                        "id": "item-1",
                        "status": "UPDATED",
                        "executionStatus": "SUCCESS",
                        "lastUpdatedAt": "2026-09-15T12:00:00.000Z",
                        "connector": {"id": 200, "name": "Meu Pluggy"},
                    }
                )
            elif self.path.startswith("/accounts"):
                self._respond(
                    {
                        "results": [
                            {
                                "id": "account-1",
                                "itemId": "item-1",
                                "name": "Conta corrente",
                                "type": "BANK",
                                "subtype": "CHECKING_ACCOUNT",
                                "currencyCode": "BRL",
                                "balance": 1234.56,
                            }
                        ]
                    }
                )
            else:
                self._respond(
                    {
                        "results": [
                            {
                                "id": "transaction-1",
                                "accountId": "account-1",
                                "description": "Mercado",
                                "amount": -38.5,
                                "currencyCode": "BRL",
                                "date": "2026-09-15T14:30:00.000Z",
                                "type": "DEBIT",
                                "status": "POSTED",
                            }
                        ],
                        "next": None,
                    }
                )

        def do_PATCH(self) -> None:
            payload = self._payload()
            requests.append(("PATCH", self.path, payload, self.headers.get("X-API-KEY")))
            self._respond({"id": "item-1", "status": "UPDATING"})

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = PluggyClient(
            client_id="00000000-0000-0000-0000-000000000000",
            client_secret="fictitious-secret",
            base_url=f"http://127.0.0.1:{server.server_port}",
            request_timeout=2,
        )
        token = client.create_connect_token(client_user_id="personal-user")
        item = client.get_item("item-1")
        accounts = client.list_accounts("item-1")
        page = client.list_transactions("account-1")
        client.trigger_item_update("item-1")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert token == "short-lived-connect-token"
    assert item.connector_id == 200
    assert accounts[0].balance == Decimal("1234.56")
    assert page.transactions[0].amount == Decimal("-38.5")
    assert page.transactions[0].type == "DEBIT"
    assert requests[0] == (
        "POST",
        "/auth",
        {
            "clientId": "00000000-0000-0000-0000-000000000000",
            "clientSecret": "fictitious-secret",
        },
        None,
    )
    assert all(request[3] == "temporary-api-key" for request in requests[1:])
    assert requests[-1][0:3] == ("PATCH", "/items/item-1", {})
