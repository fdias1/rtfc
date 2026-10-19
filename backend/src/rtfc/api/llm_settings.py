"""Handlers de configuração de LLM: ler/gravar configurações e chaves, testar e listar modelos."""

import logging

from pydantic import BaseModel, ConfigDict

from rtfc.config import PROVIDERS, LlmRole, SecretStore, Settings, SettingsStore, get_provider
from rtfc.llm import LlmClient, LlmError, list_models
from rtfc.protocol import (
    LlmModels,
    LlmModelsResult,
    LlmRoleData,
    LlmTest,
    LlmTestResult,
    ProviderData,
    SecretSet,
    SettingsData,
    SettingsResult,
    SettingsSet,
)

log = logging.getLogger(__name__)


class _Ping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool


def _role_data(role: LlmRole) -> LlmRoleData:
    return LlmRoleData(provider=role.provider, model=role.model, base_url=role.base_url)


def settings_result(request_id: str, store: SettingsStore, secrets: SecretStore) -> SettingsResult:
    s = store.settings
    return SettingsResult(
        id=request_id,
        settings=SettingsData(
            extractor=_role_data(s.extractor),
            checker=_role_data(s.checker),
            auto_extract=s.auto_extract,
        ),
        providers=[
            ProviderData(
                id=p.id,
                label=p.label,
                needs_key=p.needs_key,
                has_key=bool(secrets.get(p.id)),
                default_base_url=p.default_base_url,
                suggested_models=list(p.suggested_models),
            )
            for p in PROVIDERS.values()
        ],
    )


def _role(data: LlmRoleData) -> LlmRole:
    get_provider(data.provider)  # valida
    if not data.model.strip():
        raise ValueError("modelo não informado")
    return LlmRole(provider=data.provider, model=data.model.strip(), base_url=data.base_url or None)


def set_settings(msg: SettingsSet, store: SettingsStore, secrets: SecretStore) -> SettingsResult:
    store.save(
        Settings(
            extractor=_role(msg.settings.extractor),
            checker=_role(msg.settings.checker),
            auto_extract=msg.settings.auto_extract,
        )
    )
    return settings_result(msg.id, store, secrets)


def set_secret(msg: SecretSet, store: SettingsStore, secrets: SecretStore) -> SettingsResult:
    # Além dos provedores de LLM, aceita as chaves da busca (M6).
    if msg.provider not in ("tavily",):
        get_provider(msg.provider)
    value = (msg.value or "").strip()
    if value:
        secrets.set(msg.provider, value)
    else:
        secrets.delete(msg.provider)
    return settings_result(msg.id, store, secrets)


async def test_llm(msg: LlmTest, store: SettingsStore, secrets: SecretStore) -> LlmTestResult:
    role = _role(msg.config) if msg.config else getattr(store.settings, msg.role)
    client = LlmClient(role, secrets, timeout_s=30)
    try:
        result = await client.structured(
            [
                {"role": "system", "content": "Você é um teste de conexão."},
                {"role": "user", "content": 'Responda com {"ok": true}.'},
            ],
            _Ping,
        )
    except (LlmError, ValueError) as exc:
        return LlmTestResult(id=msg.id, ok=False, model=client.litellm_model, message=str(exc))
    return LlmTestResult(
        id=msg.id, ok=True, model=result.model, latency_ms=result.latency_ms, message=None
    )


async def models(msg: LlmModels, secrets: SecretStore) -> LlmModelsResult:
    try:
        found = await list_models(msg.provider, secrets, msg.base_url)
    except Exception as exc:
        log.info("listar modelos de %s falhou: %s", msg.provider, exc)
        fallback = list(get_provider(msg.provider).suggested_models)
        return LlmModelsResult(
            id=msg.id, provider=msg.provider, models=fallback, message=str(exc)[:200]
        )
    return LlmModelsResult(id=msg.id, provider=msg.provider, models=found)
