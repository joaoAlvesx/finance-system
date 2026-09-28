import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.integrations.telegram import TelegramBotClient


def test_client_uses_bot_api_without_exposing_transport_details() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            requests.append((self.path, payload))
            if self.path.endswith("/sendMessage"):
                result: object = {"message_id": 42}
            else:
                result = [
                    {
                        "update_id": 9,
                        "message": {"chat": {"id": 123456}, "text": "/saldo"},
                    }
                ]
            body = json.dumps({"ok": True, "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = TelegramBotClient(
            token="fake-token",
            base_url=f"http://127.0.0.1:{server.server_port}",
            request_timeout=2,
        )
        assert client.send_message(chat_id="123456", text="mensagem segura") == "42"
        updates = client.get_updates(offset=9, timeout=0)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert updates[0].chat_id == "123456"
    assert updates[0].text == "/saldo"
    assert requests == [
        (
            "/botfake-token/sendMessage",
            {"chat_id": "123456", "text": "mensagem segura"},
        ),
        (
            "/botfake-token/getUpdates",
            {"timeout": 0, "allowed_updates": ["message"], "offset": 9},
        ),
    ]
