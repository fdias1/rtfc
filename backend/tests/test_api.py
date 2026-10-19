import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rtfc import __version__
from rtfc.api import create_app
from rtfc.api.app import WS_CLOSE_UNAUTHORIZED

TOKEN = "test-token"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(TOKEN))


def test_health_requires_token(client: TestClient) -> None:
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_accepts_bearer_and_query(client: TestClient) -> None:
    r = client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.json()["version"] == __version__
    assert client.get(f"/health?token={TOKEN}").status_code == 200


def test_ws_rejects_bad_token(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/ws?token=wrong") as ws,
    ):
        ws.receive_text()
    assert exc.value.code == WS_CLOSE_UNAUTHORIZED


def test_ws_hello_ping_echo(client: TestClient) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"
        assert hello["protocol_version"] == 1

        ws.send_text(json.dumps({"type": "ping", "id": "1"}))
        assert json.loads(ws.receive_text()) == {"type": "pong", "id": "1"}

        ws.send_text(json.dumps({"type": "echo", "id": "2", "text": "olá"}))
        assert json.loads(ws.receive_text()) == {"type": "echo.reply", "id": "2", "text": "olá"}


def test_ws_invalid_message_returns_error(client: TestClient) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"type": "nope"}))
        reply = json.loads(ws.receive_text())
        assert reply["type"] == "error"
        assert reply["code"] == "invalid_message"
