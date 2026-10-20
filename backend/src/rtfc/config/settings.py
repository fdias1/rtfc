"""Configurações persistidas em `settings.json` (sem segredos: as chaves ficam no keyring)."""

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rtfc.config.secrets import SecretStore

log = logging.getLogger(__name__)


class LlmRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    base_url: str | None = None


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["searxng", "duckduckgo", "tavily"] = "searxng"
    searxng_url: str = "http://127.0.0.1:8888"
    fallback_duckduckgo: bool = True
    """Se o provedor principal falhar, tenta o DuckDuckGo (sem conta)."""
    blocked_domains: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    extractor: LlmRole = Field(default_factory=lambda: LlmRole(provider="ollama", model="qwen3:8b"))
    """Extrai as afirmações a cada frase: precisa ser rápido (ver ADR 0004)."""
    checker: LlmRole = Field(default_factory=lambda: LlmRole(provider="ollama", model="qwen3:8b"))
    """Analisa as evidências e dá o veredicto (M6)."""
    reviewer: LlmRole = Field(default_factory=lambda: LlmRole(provider="ollama", model="qwen3:14b"))
    """Recheca depois da sessão, com o Whisper fora da memória (M6.1): pode ser maior/mais lento."""
    auto_review: bool = False
    """Rechecar automaticamente com o revisor ao encerrar uma sessão."""
    auto_extract: bool = True
    auto_check: bool = True
    """Checa automaticamente cada afirmação extraída."""
    search: SearchSettings = Field(default_factory=SearchSettings)
    check_concurrency: int = Field(default=3, ge=1, le=8)
    min_claim_score: int = Field(default=4, ge=1, le=5)
    """Só registra afirmações com nota de relevância/checabilidade ≥ este valor (ADR 0006)."""
    diarization: bool = True
    """Identifica os falantes (M4, ADR 0008)."""
    speaker_threshold: float = Field(default=0.6, ge=0.2, le=0.9)
    """Similaridade mínima para dois trechos serem do mesmo falante. Maior = separa mais."""


LOCAL_EXTRACTOR = LlmRole(provider="ollama", model="qwen3:8b")


def default_settings(secrets: SecretStore | None) -> Settings:
    """Padrão de fábrica: tudo local (Ollama qwen3:8b), sem custo nem envio de texto para fora.

    O 8B é o maior que cabe ao vivo junto com o Whisper num Mac de 16 GB: com o 14B
    (10 GB) a máquina entrou em swap e a transcrição travou (ADR 0007). O 14B segue
    disponível nas configurações para máquinas com mais memória.

    Provedores online (OpenAI, Claude, Gemini…) continuam disponíveis nas configurações;
    são mais rápidos e acertam mais (ADR 0004/0007), mas têm custo.
    """
    return Settings()


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
