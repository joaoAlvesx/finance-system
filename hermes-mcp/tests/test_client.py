import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from finance_mcp.client import FinanceAPIClient


class Handler(BaseHTTPRequestHandler):
    received_path = ""
    received_authorization = ""

    def do_GET(self) -> None:
        type(self).received_path = self.path
        type(self).received_authorization = self.headers.get("Authorization", "")
        body = json.dumps({"balance": "42.00"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_client_sends_scoped_token_and_query_to_internal_api() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        client = FinanceAPIClient(
            f"http://127.0.0.1:{server.server_port}", "fst_test_token"
        )
        result = client.request("GET", "/balance", query={"account_id": "abc"})
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert result == {"balance": "42.00"}
    assert Handler.received_path == "/api/v1/assistant/tools/balance?account_id=abc"
    assert Handler.received_authorization == "Bearer fst_test_token"
