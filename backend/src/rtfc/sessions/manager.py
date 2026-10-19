"""Sessões: cada uma é uma pasta com `session.json` (+ `audio.ogg` nas sessões ao vivo)."""

import asyncio
import contextlib
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from rtfc.audio import ffmpeg
from rtfc.audio.ring_buffer import PcmRingBuffer
from rtfc.audio.sources import AudioSourceError, FileDecoder, LiveRecorder
from rtfc.protocol import SessionEnded, SessionInfo, SessionProgress

log = logging.getLogger(__name__)

EventSink = Callable[[SessionProgress | SessionEnded], Awaitable[None]]

LIVE_PROGRESS_EVERY_MS = 1000


class SessionError(RuntimeError):
    pass


def default_sessions_dir() -> Path:
    override = os.environ.get("RTFC_SESSIONS_DIR")
    return Path(override) if override else Path.home() / "Documents" / "rtfc" / "sessions"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Session:
    def __init__(self, info: SessionInfo, emit: EventSink) -> None:
        self.info = info
        self.buffer = PcmRingBuffer()
        self._emit = emit
        self.recorder: LiveRecorder | None = None
        self.task: asyncio.Task[None] | None = None
        self._last_progress_ms = 0

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def is_live(self) -> bool:
        return self.info.source != "file"

    def save(self) -> None:
        path = Path(self.info.dir) / "session.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self.info.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    async def push_pcm(self, pcm: bytes) -> None:
        if self.recorder is None:
            raise SessionError("sessão não recebe áudio da UI")
        await self.recorder.write(pcm)
        ms = self.recorder.duration_ms
        if ms - self._last_progress_ms >= LIVE_PROGRESS_EVERY_MS:
            self._last_progress_ms = ms
            await self._emit(SessionProgress(session_id=self.id, processed_ms=ms))

    async def emit(self, event: SessionProgress | SessionEnded) -> None:
        await self._emit(event)


class SessionManager:
    def __init__(self, sessions_dir: Path | None = None) -> None:
        self.sessions_dir = sessions_dir or default_sessions_dir()
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionError(f"sessão desconhecida: {session_id}") from None

    def _new_info(self, source: str, **extra: object) -> SessionInfo:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{stamp}-{source}-{secrets.token_hex(2)}"
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        return SessionInfo.model_validate(
            {
                "id": session_id,
                "source": source,
                "status": "recording",
                "dir": str(session_dir),
                "audio_path": str(session_dir / "audio.ogg"),
                "started_at": _now(),
                **extra,
            }
        )

    async def start_live(
        self, source: str, emit: EventSink, sample_rate: int = 48_000, backend_capture: bool = False
    ) -> Session:
        if source not in ("mic", "system"):
            raise SessionError(f"fonte ao vivo inválida: {source}")
        session = Session(self._new_info(source), emit)
        session.recorder = LiveRecorder(
            Path(session.info.audio_path), session.buffer.write, input_rate=sample_rate
        )
        try:
            if backend_capture:
                await session.recorder.start_backend_capture()
            else:
                await session.recorder.start()
        except (OSError, ffmpeg.FfmpegNotFoundError) as exc:
            raise SessionError(f"não foi possível iniciar a gravação: {exc}") from exc
        session.save()
        self._sessions[session.id] = session
        return session

    async def start_file(self, file_path: str, emit: EventSink) -> Session:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise SessionError(f"arquivo não encontrado: {path}")
        try:
            media = await ffmpeg.probe(path)
        except (ValueError, ffmpeg.FfmpegNotFoundError) as exc:
            raise SessionError(f"não foi possível ler o arquivo: {exc}") from exc
        if not media.has_audio:
            raise SessionError("o arquivo não tem trilha de áudio")

        info = self._new_info(
            "file",
            status="processing",
            audio_path=str(path),
            file_path=str(path),
            media_kind="video" if media.has_video else "audio",
            duration_ms=media.duration_ms,
        )
        session = Session(info, emit)
        session.save()
        self._sessions[session.id] = session

        async def progress(ms: int) -> None:
            await session.emit(
                SessionProgress(session_id=session.id, processed_ms=ms, total_ms=media.duration_ms)
            )

        session.task = asyncio.create_task(self._run_file(session, FileDecoder(path, session.buffer.write, progress)))
        return session

    async def _run_file(self, session: Session, decoder: FileDecoder) -> None:
        try:
            duration = await decoder.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("falha ao decodificar %s", decoder.path)
            await self._finish(session, "error", error=str(exc))
            return
        session.info.duration_ms = duration
        await self._finish(session, "completed")

    async def stop(self, session_id: str, request_id: str | None = None) -> SessionEnded:
        session = self.get(session_id)
        if session.recorder is not None:
            await session.recorder.stop()
            session.info.duration_ms = session.recorder.duration_ms
        if session.task is not None and not session.task.done():
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
        return await self._finish(session, "stopped", request_id=request_id, notify=False)

    async def _finish(
        self,
        session: Session,
        reason: str,
        *,
        error: str | None = None,
        request_id: str | None = None,
        notify: bool = True,
    ) -> SessionEnded:
        self._sessions.pop(session.id, None)
        session.info.status = "error" if reason == "error" else "completed"
        session.info.ended_at = _now()
        session.save()
        event = SessionEnded.model_validate(
            {"id": request_id, "session": session.info, "reason": reason, "error": error}
        )
        if notify:
            with contextlib.suppress(Exception):
                await session.emit(event)
        return event

    async def stop_all(self, session_ids: list[str] | None = None) -> None:
        for sid in list(session_ids if session_ids is not None else self._sessions):
            if sid in self._sessions:
                with contextlib.suppress(Exception):
                    await self.stop(sid)


__all__ = ["AudioSourceError", "Session", "SessionError", "SessionManager"]
