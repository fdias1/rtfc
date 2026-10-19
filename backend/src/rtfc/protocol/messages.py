"""Mensagens JSON trocadas pelo WebSocket `/ws`.

Toda mensagem tem um campo `type` (discriminador). Mensagens que esperam
resposta carregam um `id`, repetido na resposta.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION = 1


class _Message(BaseModel):
    # Campos com default (como `type`) saem como obrigatórios no schema: os dois lados
    # sempre enviam `type`, e o TS precisa dele obrigatório para estreitar a união.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


# --- Tipos compartilhados -----------------------------------------------------

SourceKind = Literal["mic", "system", "file"]
SessionStatus = Literal["recording", "processing", "completed", "interrupted", "error"]


class SessionInfo(_Message):
    """Estado de uma sessão (também é o conteúdo de `session.json` na pasta da sessão)."""

    id: str
    source: SourceKind
    status: SessionStatus
    dir: str
    audio_path: str
    """Gravação (`audio.ogg`) nas sessões ao vivo; o arquivo original nas sessões de arquivo."""
    media_kind: Literal["audio", "video"] = "audio"
    file_path: str | None = None
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None


# --- Servidor → cliente ------------------------------------------------------


class Hello(_Message):
    """Enviada pelo servidor assim que a conexão é aceita."""

    type: Literal["hello"] = "hello"
    server_version: str
    protocol_version: int = PROTOCOL_VERSION


class Pong(_Message):
    type: Literal["pong"] = "pong"
    id: str


class EchoReply(_Message):
    type: Literal["echo.reply"] = "echo.reply"
    id: str
    text: str


class ErrorMessage(_Message):
    type: Literal["error"] = "error"
    id: str | None = None
    code: str
    message: str


class SessionStarted(_Message):
    type: Literal["session.started"] = "session.started"
    id: str
    session: SessionInfo


class SessionProgress(_Message):
    """Progresso: tempo de áudio já recebido (ao vivo) ou decodificado (arquivo)."""

    type: Literal["session.progress"] = "session.progress"
    session_id: str
    processed_ms: int
    total_ms: int | None = None


class SessionEnded(_Message):
    """Fim de uma sessão. Tem `id` quando é a resposta a um `session.stop`."""

    type: Literal["session.ended"] = "session.ended"
    id: str | None = None
    session: SessionInfo
    reason: Literal["stopped", "completed", "error"]
    error: str | None = None


ServerMessage = Annotated[
    Hello | Pong | EchoReply | ErrorMessage | SessionStarted | SessionProgress | SessionEnded,
    Field(discriminator="type"),
]


# --- Cliente → servidor ------------------------------------------------------


class Ping(_Message):
    type: Literal["ping"] = "ping"
    id: str


class EchoRequest(_Message):
    """Mensagem de exemplo do M0: o servidor devolve o mesmo texto."""

    type: Literal["echo"] = "echo"
    id: str
    text: str


class SessionStart(_Message):
    """Inicia uma sessão.

    - `mic`/`system` com `capture="ui"`: a UI envia PCM s16le mono `sample_rate` em frames
      binários no mesmo WebSocket, até o `session.stop`.
    - `system` com `capture="backend"`: o backend captura sozinho (fallback do Linux).
    - `file`: o backend decodifica `file_path`.
    """

    type: Literal["session.start"] = "session.start"
    id: str
    source: SourceKind
    capture: Literal["ui", "backend"] = "ui"
    sample_rate: int = Field(default=48_000, ge=8_000, le=192_000)
    file_path: str | None = None


class SessionStop(_Message):
    type: Literal["session.stop"] = "session.stop"
    id: str
    session_id: str


AnyClientMessage = Ping | EchoRequest | SessionStart | SessionStop
ClientMessage = Annotated[AnyClientMessage, Field(discriminator="type")]

_client_adapter: TypeAdapter[AnyClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str | bytes) -> AnyClientMessage:
    """Valida e converte uma mensagem JSON do cliente. Levanta `ValidationError`."""
    return _client_adapter.validate_json(raw)
