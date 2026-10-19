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
    title: str | None = None
    """Nome dado pelo usuário; a UI mostra a data e a fonte quando vazio."""
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
    language: str | None = None
    """Idioma do discurso (definido pelo usuário ou detectado na primeira fala)."""
    stt_engine: str | None = None
    stt_model: str | None = None


class TranscriptWord(_Message):
    text: str
    start_ms: int
    end_ms: int
    prob: float


class TranscriptSegmentData(_Message):
    index: int
    start_ms: int
    end_ms: int
    text: str
    words: list[TranscriptWord]
    speaker: str | None = None


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


class SessionUpdated(_Message):
    """Metadados da sessão mudaram (idioma detectado, título renomeado…).

    Tem `id` quando é a resposta a um `session.rename`.
    """

    type: Literal["session.updated"] = "session.updated"
    id: str | None = None
    session: SessionInfo


class SessionListItem(_Message):
    session: SessionInfo
    size_bytes: int
    """Espaço da pasta da sessão (não conta o arquivo original das sessões de arquivo)."""
    segment_count: int


class SessionListResult(_Message):
    type: Literal["session.list.result"] = "session.list.result"
    id: str
    sessions: list[SessionListItem]


class SessionDeleted(_Message):
    type: Literal["session.deleted"] = "session.deleted"
    id: str
    session_id: str


class TranscriptSegment(_Message):
    """Um segmento (frase) confirmado. Não muda mais."""

    type: Literal["transcript.segment"] = "transcript.segment"
    session_id: str
    segment: TranscriptSegmentData
    latency_ms: int | None = None
    """Ao vivo: tempo entre o fim da fala e a confirmação do segmento."""


class TranscriptPartial(_Message):
    """Trecho ainda aberto: `confirmed` não muda mais; `tentative` pode mudar na próxima passada."""

    type: Literal["transcript.partial"] = "transcript.partial"
    session_id: str
    start_ms: int
    confirmed: str
    tentative: str


class TranscriptResult(_Message):
    type: Literal["transcript.result"] = "transcript.result"
    id: str
    session_id: str
    segments: list[TranscriptSegmentData]


class SttStatusMessage(_Message):
    """Estado do modelo de transcrição (download, carregamento, pronto, erro)."""

    type: Literal["stt.status"] = "stt.status"
    state: Literal["idle", "downloading", "loading", "ready", "error"]
    engine: str
    model: str
    progress: float | None = None
    message: str | None = None


ServerMessage = Annotated[
    Hello
    | Pong
    | EchoReply
    | ErrorMessage
    | SessionStarted
    | SessionProgress
    | SessionEnded
    | SessionUpdated
    | SessionListResult
    | SessionDeleted
    | TranscriptSegment
    | TranscriptPartial
    | TranscriptResult
    | SttStatusMessage,
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
    language: str | None = "pt"
    """Código ISO 639-1 do idioma do discurso; `None` = detectar automaticamente."""


class SessionStop(_Message):
    type: Literal["session.stop"] = "session.stop"
    id: str
    session_id: str


class TranscriptGet(_Message):
    """Pede a transcrição completa de uma sessão (ao reabrir)."""

    type: Literal["transcript.get"] = "transcript.get"
    id: str
    session_id: str


class SessionList(_Message):
    """Lista as sessões salvas, da mais recente para a mais antiga."""

    type: Literal["session.list"] = "session.list"
    id: str


class SessionRename(_Message):
    type: Literal["session.rename"] = "session.rename"
    id: str
    session_id: str
    title: str | None = Field(default=None, max_length=200)


class SessionDelete(_Message):
    """Apaga a pasta da sessão e a transcrição. Nunca toca no arquivo original."""

    type: Literal["session.delete"] = "session.delete"
    id: str
    session_id: str


AnyClientMessage = (
    Ping
    | EchoRequest
    | SessionStart
    | SessionStop
    | TranscriptGet
    | SessionList
    | SessionRename
    | SessionDelete
)
ClientMessage = Annotated[AnyClientMessage, Field(discriminator="type")]

_client_adapter: TypeAdapter[AnyClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str | bytes) -> AnyClientMessage:
    """Valida e converte uma mensagem JSON do cliente. Levanta `ValidationError`."""
    return _client_adapter.validate_json(raw)
