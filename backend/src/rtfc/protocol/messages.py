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


ServerMessage = Annotated[Hello | Pong | EchoReply | ErrorMessage, Field(discriminator="type")]


# --- Cliente → servidor ------------------------------------------------------


class Ping(_Message):
    type: Literal["ping"] = "ping"
    id: str


class EchoRequest(_Message):
    """Mensagem de exemplo do M0: o servidor devolve o mesmo texto."""

    type: Literal["echo"] = "echo"
    id: str
    text: str


ClientMessage = Annotated[Ping | EchoRequest, Field(discriminator="type")]

_client_adapter: TypeAdapter[Ping | EchoRequest] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str | bytes) -> Ping | EchoRequest:
    """Valida e converte uma mensagem JSON do cliente. Levanta `ValidationError`."""
    return _client_adapter.validate_json(raw)
