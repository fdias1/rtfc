"""Configurações de LLM e chaves pelo WebSocket (cofre em memória; nada toca no keyring real)."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from rtfc.api import create_app
from rtfc.config import LlmRole, MemorySecretStore, SettingsStore
from rtfc.llm.client import LlmClient, LlmConfigError
from rtfc.sessions import SessionManager

TOKEN = "t"


def ask(ws: WebSocketTestSession, msg: dict[str, Any]) -> dict[str, Any]:
    ws.send_text(json.dumps(msg))
    while True:
        reply: dict[str, Any] = json.loads(ws.receive_text())
        if reply.get("id") == msg["id"]:
            return reply


@pytest.fixture
def secrets() -> MemorySecretStore:
    return MemorySecretStore()


@pytest.fixture
def client(tmp_path: Path, secrets: MemorySecretStore) -> TestClient:
    manager = SessionManager(
        tmp_path / "sessions",
        settings=SettingsStore(tmp_path / "settings.json", secrets),
        secrets=secrets,
    )
    return TestClient(create_app(TOKEN, sessions=manager))


def test_settings_roundtrip_and_keys_never_returned(
    client: TestClient, secrets: MemorySecretStore, tmp_path: Path
) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_text()  # hello
        got = ask(ws, {"type": "settings.get", "id": "1"})
        assert got["settings"]["extractor"] == {
            "provider": "ollama",
            "model": "qwen3:8b",
            "base_url": None,
        }
        openai = next(p for p in got["providers"] if p["id"] == "openai")
        assert openai["has_key"] is False

        got = ask(
            ws, {"type": "secret.set", "id": "2", "provider": "openai", "value": " sk-test-123 "}
        )
        assert next(p for p in got["providers"] if p["id"] == "openai")["has_key"] is True
        assert secrets.values["openai"] == "sk-test-123"
        assert "sk-test" not in json.dumps(got)

        new = got["settings"] | {
            "extractor": {"provider": "openai", "model": "gpt-5.4-mini", "base_url": None}
        }
        got = ask(ws, {"type": "settings.set", "id": "3", "settings": new})
        assert got["settings"]["extractor"]["provider"] == "openai"

        bad = new | {"checker": {"provider": "nao-existe", "model": "x", "base_url": None}}
        assert ask(ws, {"type": "settings.set", "id": "4", "settings": bad})["type"] == "error"

        got = ask(ws, {"type": "secret.set", "id": "5", "provider": "openai", "value": None})
        assert "openai" not in secrets.values

    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["extractor"]["model"] == "gpt-5.4-mini"
    assert "sk-test" not in (tmp_path / "settings.json").read_text()


def test_llm_test_reports_missing_key(client: TestClient) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_text()
        reply = ask(
            ws,
            {
                "type": "llm.test",
                "id": "1",
                "role": "checker",
                "config": {"provider": "openai", "model": "gpt-5.4-mini", "base_url": None},
            },
        )
    assert reply["ok"] is False
    assert "chave" in reply["message"]


def test_client_requires_key_for_hosted_providers() -> None:
    with pytest.raises(LlmConfigError):
        LlmClient(LlmRole(provider="anthropic", model="x"), MemorySecretStore())._call_kwargs()
    kwargs = LlmClient(
        LlmRole(provider="ollama", model="qwen3:8b"), MemorySecretStore()
    )._call_kwargs()
    assert kwargs["api_base"] == "http://127.0.0.1:11434"
    assert kwargs["think"] is False


def test_default_extractor_follows_openai_key(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    store = SettingsStore(tmp_path / "settings.json", secrets)
    assert store.settings.extractor.provider == "ollama"
    secrets.set("openai", "sk-x")
    assert store.settings.extractor.provider == "openai"
    assert store.settings.extractor.model == "gpt-5.4-mini"
    # Depois de salvar, vale a escolha do usuário, com ou sem chave.
    local = LlmRole(provider="ollama", model="qwen3:8b")
    store.save(store.settings.model_copy(update={"extractor": local}))
    assert SettingsStore(tmp_path / "settings.json", secrets).settings.extractor == local


async def test_foreign_script_is_sent_back_for_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import BaseModel

    class Out(BaseModel):
        text: str

    replies = iter(['{"text": "Não há nome do বক্তা."}', '{"text": "Não há nome do orador."}'])
    client = LlmClient(LlmRole(provider="ollama", model="x"), MemorySecretStore())

    async def fake_complete(messages: Any, kwargs: Any) -> str:
        return next(replies)

    monkeypatch.setattr(client, "_complete", fake_complete)
    result = await client.structured([{"role": "user", "content": "oi"}], Out)
    assert result.value.text == "Não há nome do orador."
