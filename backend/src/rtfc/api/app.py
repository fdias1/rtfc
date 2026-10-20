"""Aplicação FastAPI: HTTP para consultas simples e WebSocket para stream/eventos.

O backend só escuta em 127.0.0.1 e exige o token gerado pelo processo main
do Electron em todas as rotas (header `Authorization: Bearer` ou `?token=`).

No WebSocket, frames de texto são mensagens JSON do protocolo; frames binários são
PCM s16le mono da sessão ao vivo ativa nesta conexão (ver `SessionStart`).
"""

import asyncio
import logging
import secrets
from typing import Annotated

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocketState

from rtfc import __version__
from rtfc.api import llm_settings
from rtfc.audio.sources import AudioSourceError
from rtfc.config import (
    KeyringSecretStore,
    LlmRole,
    MemorySecretStore,
    SecretStore,
    Settings,
    SettingsStore,
)
from rtfc.diarization import DiarizationService
from rtfc.llm.fake import fake_enabled
from rtfc.protocol import (
    PROTOCOL_VERSION,
    CheckCancel,
    CheckRetry,
    ClaimDiscard,
    ClaimManual,
    ClaimsGet,
    ClaimsResult,
    ClaimUpdated,
    EchoReply,
    EchoRequest,
    ErrorMessage,
    Hello,
    LlmModels,
    LlmTest,
    Ping,
    Pong,
    ReviewCancel,
    ReviewGet,
    ReviewStart,
    SearchTest,
    SecretSet,
    SessionDelete,
    SessionDeleted,
    SessionEnded,
    SessionExport,
    SessionExportResult,
    SessionGenerateContext,
    SessionList,
    SessionListResult,
    SessionRename,
    SessionSetContext,
    SessionStart,
    SessionStarted,
    SessionStop,
    SessionUpdated,
    SettingsGet,
    SettingsSet,
    SpeakerRename,
    SpeakersRefine,
    SttStatusMessage,
    TranscriptGet,
    TranscriptResult,
    parse_client_message,
)
from rtfc.sessions import Session, SessionError, SessionManager, default_sessions_dir
from rtfc.storage import TranscriptStore
from rtfc.stt.service import SttService, SttStatus

log = logging.getLogger(__name__)

# Código de fechamento para token inválido (faixa 4000–4999 é livre para aplicações).
WS_CLOSE_UNAUTHORIZED = 4401


def create_app(token: str, sessions: SessionManager | None = None) -> FastAPI:
    app = FastAPI(title="rtfc backend", version=__version__, docs_url=None, redoc_url=None)
    manager = sessions or default_manager()
    preload: dict[str, asyncio.Task[object]] = {}

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
        return {
            "status": "ok",
            "version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "sessions_dir": str(manager.sessions_dir),
        }

    @app.websocket("/ws")
    async def ws(
        websocket: WebSocket, token_param: Annotated[str | None, Query(alias="token")] = None
    ) -> None:
        if not _valid(token_param):
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
            return
        await websocket.accept()
        conn = _Connection(websocket, manager)
        await conn.send(Hello(server_version=__version__))
        if manager.stt is not None:
            await conn.send_stt(manager.stt.status)
            # Carrega (e baixa, na primeira vez) o modelo assim que a UI conecta, para a
            # primeira sessão não esperar.
            if "stt" not in preload:
                preload["stt"] = asyncio.create_task(_preload(manager.stt))
        try:
            await conn.run()
        finally:
            # Protegido contra cancelamento: finalizar o .ogg e o session.json é obrigatório
            # mesmo quando o servidor derruba a conexão.
            with anyio.CancelScope(shield=True):
                await conn.close()

    return app


def default_manager() -> SessionManager:
    sessions_dir = default_sessions_dir()
    data_dir = sessions_dir.parent
    # Em teste, cofre em memória: nunca lê nem grava as chaves reais do usuário (e o
    # Keychain de um runner de CI pode travar esperando desbloqueio).
    secret_store: SecretStore = MemorySecretStore() if fake_enabled() else KeyringSecretStore()
    settings = SettingsStore(data_dir / "settings.json", secret_store)
    if fake_enabled() and not settings.path.exists():
        # E2E: extração determinística, sem rede nem modelo local.
        fake = LlmRole(provider="fake", model="fake")
        reviewer = LlmRole(provider="fake", model="fake-review")
        settings.save(Settings(extractor=fake, checker=fake, reviewer=reviewer))
    return SessionManager(
        sessions_dir,
        stt=SttService(),
        store=TranscriptStore(data_dir / "rtfc.sqlite"),
        settings=settings,
        secrets=secret_store,
        diarization=DiarizationService(),
    )


async def _preload(stt: SttService) -> object:
    try:
        return await stt.ensure_ready()
    except Exception:
        return None  # o erro já foi enviado como stt.status


class _Connection:
    """Uma conexão da UI. As sessões abertas por ela terminam quando ela fecha."""

    def __init__(self, websocket: WebSocket, manager: SessionManager) -> None:
        self.ws = websocket
        self.manager = manager
        self._send_lock = asyncio.Lock()
        self._owned: list[str] = []
        self._live: Session | None = None
        self._warned_no_live = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._unsubscribe = manager.stt.subscribe(self.send_stt) if manager.stt else None
        manager.add_listener(self.send)

    async def send_stt(self, status: SttStatus) -> None:
        await self.send(
            SttStatusMessage(
                state=status.state,
                engine=status.engine,
                model=status.model,
                progress=status.progress,
                message=status.message,
            )
        )

    async def send(self, msg: BaseModel) -> None:
        if self.ws.client_state != WebSocketState.CONNECTED:
            return
        async with self._send_lock:
            await self.ws.send_text(msg.model_dump_json())

    async def emit(self, event: BaseModel) -> None:
        if isinstance(event, SessionEnded) and self._live and self._live.id == event.session.id:
            self._live = None
        await self.send(event)

    async def run(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if (data := message.get("bytes")) is not None:
                await self._on_audio(data)
            elif (text := message.get("text")) is not None:
                reply = await self._on_text(text)
                if reply is not None:
                    await self.send(reply)

    async def close(self) -> None:
        self.manager.remove_listener(self.send)
        if self._unsubscribe:
            self._unsubscribe()
        self._live = None
        await self.manager.stop_all(self._owned)

    async def _on_audio(self, pcm: bytes) -> None:
        session = self._live
        if session is None:
            if not self._warned_no_live:
                self._warned_no_live = True
                await self.send(
                    ErrorMessage(code="no_live_session", message="áudio sem sessão ativa")
                )
            return
        try:
            await session.push_pcm(pcm)
        except (SessionError, AudioSourceError) as exc:
            log.error("gravação falhou: %s", exc)
            self._live = None
            await self.send(ErrorMessage(code="recording_failed", message=str(exc)))

    async def _on_text(self, raw: str) -> BaseModel | None:
        try:
            msg = parse_client_message(raw)
        except ValidationError as exc:
            return ErrorMessage(code="invalid_message", message=str(exc.errors()[:1]))
        try:
            match msg:
                case Ping():
                    return Pong(id=msg.id)
                case EchoRequest():
                    return EchoReply(id=msg.id, text=msg.text)
                case SessionStart():
                    return await self._start(msg)
                case SessionStop():
                    ended = await self.manager.stop(msg.session_id, request_id=msg.id)
                    # A resposta ao stop não passa por emit(): liberar a sessão ao vivo aqui,
                    # senão a próxima sessão ao vivo desta conexão é recusada.
                    if self._live and self._live.id == msg.session_id:
                        self._live = None
                    return ended
                case SessionList():
                    return SessionListResult(id=msg.id, sessions=await self.manager.list_sessions())
                case SessionRename():
                    info = await self.manager.rename(msg.session_id, msg.title)
                    return SessionUpdated(id=msg.id, session=info)
                case SessionDelete():
                    await self.manager.delete(msg.session_id)
                    return SessionDeleted(id=msg.id, session_id=msg.session_id)
                case SessionSetContext():
                    info = await self.manager.set_context(msg.session_id, msg.context)
                    return SessionUpdated(id=msg.id, session=info)
                case SessionGenerateContext():
                    info = await self.manager.generate_context(msg.session_id)
                    return SessionUpdated(id=msg.id, session=info)
                case TranscriptGet():
                    return TranscriptResult(
                        id=msg.id,
                        session_id=msg.session_id,
                        segments=self.manager.transcript(msg.session_id),
                    )
                case ClaimsGet():
                    return ClaimsResult(
                        id=msg.id,
                        session_id=msg.session_id,
                        claims=self.manager.claims(msg.session_id),
                    )
                case ClaimManual():
                    claim = await self.manager.manual_claim(
                        msg.session_id, msg.from_segment, msg.from_word, msg.to_segment, msg.to_word
                    )
                    return ClaimUpdated(id=msg.id, claim=self.manager.claim_data(claim))
                case ClaimDiscard():
                    claim = await self.manager.discard_claim(msg.claim_id)
                    return ClaimUpdated(id=msg.id, claim=self.manager.claim_data(claim))
                case ReviewStart() | ReviewCancel() | ReviewGet():
                    if self.manager.review is None:
                        raise SessionError("revisão indisponível")
                    self.manager.load_info(msg.session_id)  # valida a sessão
                    if isinstance(msg, ReviewStart):
                        status = await self.manager.review.start(msg.session_id, msg.scope)
                    elif isinstance(msg, ReviewCancel):
                        status = await self.manager.review.cancel(msg.session_id)
                    else:
                        status = self.manager.review.status(msg.session_id)
                    return status.model_copy(update={"id": msg.id})
                case SessionExport():
                    name, content = self.manager.export(msg.session_id, msg.format)
                    return SessionExportResult(
                        id=msg.id,
                        session_id=msg.session_id,
                        format=msg.format,
                        filename=name,
                        content=content,
                    )
                case SpeakerRename():
                    info = await self.manager.rename_speaker(msg.session_id, msg.speaker, msg.name)
                    return SessionUpdated(id=msg.id, session=info)
                case SpeakersRefine():
                    # Pode levar minutos: roda à parte para não travar esta conexão.
                    task = asyncio.create_task(self._refine_speakers(msg))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                    return None
                case CheckCancel() | CheckRetry():
                    if self.manager.checks is None:
                        raise SessionError("checagem indisponível")
                    if isinstance(msg, CheckCancel):
                        claim = await self.manager.checks.cancel(msg.claim_id)
                    else:
                        claim = await self.manager.checks.retry(msg.claim_id)
                    return ClaimUpdated(id=msg.id, claim=self.manager.claim_data(claim))
                case (
                    SettingsGet()
                    | SettingsSet()
                    | SecretSet()
                    | LlmTest()
                    | LlmModels()
                    | SearchTest()
                ):
                    return await self._llm_settings(msg)
        except SessionError as exc:
            return ErrorMessage(id=msg.id, code="session_error", message=str(exc))
        except ValueError as exc:
            return ErrorMessage(id=msg.id, code="invalid_request", message=str(exc))
        return None

    async def _refine_speakers(self, msg: SpeakersRefine) -> None:
        reply: BaseModel
        try:
            reply = await self.manager.refine_speakers(msg.session_id, request_id=msg.id)
        except SessionError as exc:
            reply = ErrorMessage(id=msg.id, code="session_error", message=str(exc))
        except Exception as exc:
            log.exception("refinamento de falantes falhou")
            reply = ErrorMessage(id=msg.id, code="internal_error", message=str(exc))
        await self.send(reply)

    async def _llm_settings(
        self, msg: SettingsGet | SettingsSet | SecretSet | LlmTest | LlmModels | SearchTest
    ) -> BaseModel:
        store, secrets = self.manager.settings, self.manager.secrets
        if store is None or secrets is None:
            return ErrorMessage(
                id=msg.id, code="unavailable", message="configurações indisponíveis"
            )
        match msg:
            case SettingsGet():
                return llm_settings.settings_result(msg.id, store, secrets)
            case SettingsSet():
                return llm_settings.set_settings(msg, store, secrets)
            case SecretSet():
                return llm_settings.set_secret(msg, store, secrets)
            case LlmTest():
                return await llm_settings.test_llm(msg, store, secrets)
            case LlmModels():
                return await llm_settings.models(msg, secrets)
            case SearchTest():
                return await llm_settings.test_search(msg, secrets)

    async def _start(self, msg: SessionStart) -> SessionStarted:
        if msg.source == "file":
            if not msg.file_path:
                raise SessionError("file_path é obrigatório para sessões de arquivo")
            session = await self.manager.start_file(
                msg.file_path, self.emit, language=msg.language, context=msg.context
            )
        else:
            if msg.capture == "ui" and self._live is not None:
                raise SessionError("já existe uma sessão ao vivo nesta conexão")
            session = await self.manager.start_live(
                msg.source,
                self.emit,
                sample_rate=msg.sample_rate,
                backend_capture=msg.capture == "backend",
                language=msg.language,
                context=msg.context,
            )
            if msg.capture == "ui":
                self._live = session
                self._warned_no_live = False
        self._owned.append(session.id)
        return SessionStarted(id=msg.id, session=session.info)
