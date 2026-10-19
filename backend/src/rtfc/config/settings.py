"""Configurações persistidas em `settings.json` (sem segredos: as chaves ficam no keyring)."""

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from rtfc.config.secrets import SecretStore

log = logging.getLogger(__name__)


class LlmRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    base_url: str | None = None


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    extractor: LlmRole = Field(
        default_factory=lambda: LlmRole(provider="openai", model="gpt-5.4-mini")
    )
    """Extrai as afirmações a cada frase: precisa ser rápido (ver ADR 0004)."""
    checker: LlmRole = Field(
        default_factory=lambda: LlmRole(provider="openai", model="gpt-5.4-mini")
    )
    """Analisa as evidências e dá o veredicto (M6)."""
    auto_extract: bool = True


LOCAL_EXTRACTOR = LlmRole(provider="ollama", model="qwen3:8b")


def default_settings(secrets: SecretStore | None) -> Settings:
    """Padrão de fábrica: extração na OpenAI se houver chave; senão, local (Ollama).

    Com Whisper e um LLM de 8B dividindo a GPU de um Mac de 16 GB, a extração local passa
    de 10 s ao vivo; a online fica em ~2 s (ADR 0004). O local continua sendo opção.
    """
    settings = Settings()
    if secrets is None or not secrets.get("openai"):
        settings.extractor = LOCAL_EXTRACTOR.model_copy()
    return settings


class SettingsStore:
    def __init__(self, path: Path, secrets: SecretStore | None = None) -> None:
        self.path = path
        self._secrets = secrets
        self._saved = self._load()

    def _load(self) -> Settings | None:
        if self.path.is_file():
            try:
                return Settings.model_validate_json(self.path.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("settings.json inválido; usando o padrão")
        return None

    @property
    def settings(self) -> Settings:
        # Enquanto o usuário não salvar nada, o padrão acompanha as chaves cadastradas
        # (cadastrar a da OpenAI passa a extração para ela).
        return self._saved if self._saved is not None else default_settings(self._secrets)

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)
        self._saved = settings
