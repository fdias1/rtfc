"""Erros dos provedores viram mensagens claras, com o que fazer (M7)."""

from typing import Any

import litellm
import litellm.exceptions as e
import pytest
from pydantic import BaseModel

from rtfc.config import LlmRole, MemorySecretStore
from rtfc.llm import LlmClient, LlmConfigError, LlmError
from rtfc.llm import client as client_mod


class Ok(BaseModel):
    ok: bool


def make(provider: str, model: str) -> LlmClient:
    secrets = MemorySecretStore()
    secrets.set("openai", "sk-teste")
    return LlmClient(LlmRole(provider=provider, model=model), secrets, timeout_s=30)


CASES: list[tuple[str, BaseException, str, str]] = [
    ("openai", e.AuthenticationError("bad key", "openai", "gpt"), "auth", "chave de API inválida"),
    (
        "openai",
        e.RateLimitError("You exceeded your current quota", "openai", "gpt"),
        "quota",
        "créditos ou cota esgotados",
    ),
    (
        "openai",
        e.RateLimitError("slow down", "openai", "gpt"),
        "rate_limit",
        "limite de requisições",
    ),
    (
        "ollama",
        e.NotFoundError("model not found", "ollama", "qwen3:8b"),
        "not_found",
        "ollama pull",
    ),
    (
        "ollama",
        e.APIConnectionError("refused", "ollama", "qwen3:8b"),
        "offline",
        "Abra o app Ollama",
    ),
    ("openai", e.APIConnectionError("dns", "openai", "gpt"), "offline", "Verifique a internet"),
    ("ollama", e.Timeout("timeout", "qwen3:8b", "ollama"), "timeout", "memória livre"),
    (
        "openai",
        e.BadRequestError("maximum context length is 8192", "gpt", "openai"),
        "too_long",
        "grande demais",
    ),
]


@pytest.mark.parametrize(("provider", "exc", "kind", "text"), CASES)
async def test_provider_errors_are_explained(
    monkeypatch: pytest.MonkeyPatch, provider: str, exc: BaseException, kind: str, text: str
) -> None:
    monkeypatch.setattr(client_mod, "MAX_RETRIES", 0)
    calls = 0

    async def fail(**_: Any) -> None:
        nonlocal calls
        calls += 1
        raise exc

    monkeypatch.setattr(litellm, "acompletion", fail)
    with pytest.raises(LlmError) as info:
        await make(provider, "qwen3:8b" if provider == "ollama" else "gpt").structured(
            [{"role": "user", "content": "oi"}], Ok
        )
    assert info.value.kind == kind
    assert text in str(info.value)


async def test_quota_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fail(**_: Any) -> None:
        nonlocal calls
        calls += 1
        raise e.RateLimitError("insufficient_quota", "openai", "gpt")

    monkeypatch.setattr(litellm, "acompletion", fail)
    with pytest.raises(LlmError):
        await make("openai", "gpt").structured([{"role": "user", "content": "oi"}], Ok)
    assert calls == 1


async def test_missing_key_is_a_config_error() -> None:
    client = LlmClient(LlmRole(provider="anthropic", model="x"), MemorySecretStore())
    with pytest.raises(LlmConfigError, match="Falta a chave de API"):
        await client.structured([{"role": "user", "content": "oi"}], Ok)
