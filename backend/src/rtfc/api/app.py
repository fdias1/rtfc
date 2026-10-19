"""Aplicação FastAPI: HTTP para consultas simples e WebSocket para stream/eventos.

O backend só escuta em 127.0.0.1 e exige o token gerado pelo processo main
do Electron em todas as rotas (header `Authorization: Bearer` ou `?token=`).
"""

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from rtfc import __version__
from rtfc.protocol import (
    PROTOCOL_VERSION,
    EchoReply,
    EchoRequest,
    ErrorMessage,
    Hello,
    Ping,
    Pong,
    parse_client_message,
)

# Código de fechamento para token inválido (faixa 4000–4999 é livre para aplicações).
WS_CLOSE_UNAUTHORIZED = 4401


def create_app(token: str) -> FastAPI:
    app = FastAPI(title="rtfc backend", version=__version__, docs_url=None, redoc_url=None)

    def _valid(candidate: str | None) -> bool:
        return candidate is not None and secrets.compare_digest(candidate, token)

    def require_token(
        authorization: Annotated[str | None, Header()] = None,
        token_param: Annotated[str | None, Query(alias="token")] = None,
    ) -> None:
        bearer = authorization.removeprefix("Bearer ") if authorization else None
        if not (_valid(bearer) or _valid(token_param)):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/health", dependencies=[Depends(require_token)])
    async def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__, "protocol_version": PROTOCOL_VERSION}

    @app.websocket("/ws")
    async def ws(
        websocket: WebSocket, token_param: Annotated[str | None, Query(alias="token")] = None
    ) -> None:
        if not _valid(token_param):
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
            return
        await websocket.accept()
        await websocket.send_text(Hello(server_version=__version__).model_dump_json())
        try:
            while True:
                raw = await websocket.receive_text()
                await websocket.send_text(_handle(raw))
        except WebSocketDisconnect:
            return

    return app


def _handle(raw: str) -> str:
    try:
        msg = parse_client_message(raw)
    except ValidationError as exc:
        return ErrorMessage(code="invalid_message", message=str(exc.errors()[:1])).model_dump_json()
    match msg:
        case Ping():
            return Pong(id=msg.id).model_dump_json()
        case EchoRequest():
            return EchoReply(id=msg.id, text=msg.text).model_dump_json()
