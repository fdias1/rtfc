"""Contrato de mensagens entre a UI (Electron) e o backend.

Os modelos Pydantic daqui são a fonte da verdade: o JSON Schema gerado por
`python -m rtfc.protocol.schema` vira os tipos TS de `packages/protocol`.
"""

from rtfc.protocol.messages import (
    PROTOCOL_VERSION,
    ClientMessage,
    EchoReply,
    EchoRequest,
    ErrorMessage,
    Hello,
    Ping,
    Pong,
    ServerMessage,
    parse_client_message,
)

__all__ = [
    "PROTOCOL_VERSION",
    "ClientMessage",
    "EchoReply",
    "EchoRequest",
    "ErrorMessage",
    "Hello",
    "Ping",
    "Pong",
    "ServerMessage",
    "parse_client_message",
]
