"""Sessões: cada uma é uma pasta com `session.json`, `audio.ogg` (ao vivo) e as legendas.

Uma sessão junta a fonte de áudio (gravação ao vivo ou arquivo), a transcrição e a
persistência (SQLite + SRT/VTT), e emite os eventos do protocolo para a conexão dona.
"""

import asyncio
import contextlib
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from rtfc.audio import ffmpeg
from rtfc.audio.ring_buffer import PcmRingBuffer
from rtfc.audio.sources import AudioSourceError, FileDecoder, LiveRecorder
from rtfc.protocol import (
    SessionEnded,
    SessionInfo,
    SessionProgress,
    SessionUpdated,
    TranscriptPartial,
    TranscriptSegment,
    TranscriptSegmentData,
    TranscriptWord,
)
from rtfc.storage import StoredSegment, StoredWord, SubtitleWriter, TranscriptStore
from rtfc.stt.base import pcm16_to_float32
from rtfc.stt.files import transcribe_audio
from rtfc.stt.live import LiveTranscriber
from rtfc.stt.segmenter import Segment
from rtfc.stt.service import SttService

log = logging.getLogger(__name__)

EventSink = Callable[[BaseModel], Awaitable[None]]

LIVE_PROGRESS_EVERY_MS = 1000


class SessionError(RuntimeError):
    pass


def default_sessions_dir() -> Path:
    override = os.environ.get("RTFC_SESSIONS_DIR")
    return Path(override) if override else Path.home() / "Documents" / "rtfc" / "sessions"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def to_segment_data(seg: StoredSegment) -> TranscriptSegmentData:
    return TranscriptSegmentData(
        index=seg.index,
        start_ms=seg.start_ms,
        end_ms=seg.end_ms,
        text=seg.text,
        speaker=seg.speaker,
        words=[TranscriptWord(**w.__dict__) for w in seg.words],
    )


class Session:
    def __init__(self, info: SessionInfo, emit: EventSink, store: TranscriptStore | None) -> None:
        self.info = info
        self.buffer = PcmRingBuffer()
        self._emit = emit
        self._store = store
        self.recorder: LiveRecorder | None = None
        self.transcriber: LiveTranscriber | None = None
        self.task: asyncio.Task[None] | None = None
        self.subtitles = SubtitleWriter(Path(info.dir))
        self.segment_count = 0
        self.latencies_ms: list[int] = []
        self._last_progress_ms = 0

    @property
    def id(self) -> str:
        return self.info.id

    def save(self) -> None:
        path = Path(self.info.dir) / "session.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self.info.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    async def emit(self, event: BaseModel) -> None:
        with contextlib.suppress(Exception):
            await self._emit(event)

    async def push_pcm(self, pcm: bytes) -> None:
        if self.recorder is None:
            raise SessionError("sessão não recebe áudio da UI")
        await self.recorder.write(pcm)
        ms = self.recorder.duration_ms
        if ms - self._last_progress_ms >= LIVE_PROGRESS_EVERY_MS:
            self._last_progress_ms = ms
            await self.emit(SessionProgress(session_id=self.id, processed_ms=ms))

    # --- Callbacks da transcrição -------------------------------------------

    async def on_segment(self, seg: Segment, latency_s: float) -> None:
        stored = StoredSegment(
            index=self.segment_count,
            start_ms=round(seg.start * 1000),
            end_ms=round(seg.end * 1000),
            text=seg.text,
            words=tuple(
                StoredWord(round(w.start * 1000), round(w.end * 1000), w.text.strip(), w.prob)
                for w in seg.words
            ),
        )
        self.segment_count += 1
        if self._store:
            self._store.add_segment(self.id, stored)
        self.subtitles.add(stored.start_ms, stored.end_ms, stored.text)
        live = self.info.source != "file"
        latency_ms = round(latency_s * 1000) if live else None
        if latency_ms is not None:
            self.latencies_ms.append(latency_ms)
        await self.emit(
            TranscriptSegment(
                session_id=self.id, segment=to_segment_data(stored), latency_ms=latency_ms
            )
        )

    async def on_partial(self, start_s: float, confirmed: str, tentative: str) -> None:
        await self.emit(
            TranscriptPartial(
                session_id=self.id,
                start_ms=round(start_s * 1000),
                confirmed=confirmed,
                tentative=tentative,
            )
        )

    async def on_language(self, language: str) -> None:
        self.info.language = language
        self.save()
        await self.emit(SessionUpdated(session=self.info))


class SessionManager:
    def __init__(
        self,
        sessions_dir: Path | None = None,
        stt: SttService | None = None,
        store: TranscriptStore | None = None,
    ) -> None:
        self.sessions_dir = sessions_dir or default_sessions_dir()
        self.stt = stt
        self.store = store
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionError(f"sessão desconhecida: {session_id}") from None

    def _new_info(self, source: str, language: str | None, **extra: object) -> SessionInfo:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{stamp}-{source}-{secrets.token_hex(2)}"
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        stt_status = self.stt.status if self.stt else None
        return SessionInfo.model_validate(
            {
                "id": session_id,
                "source": source,
                "status": "recording",
                "dir": str(session_dir),
                "audio_path": str(session_dir / "audio.ogg"),
                "started_at": _now(),
                "language": language,
                "stt_engine": stt_status.engine if stt_status else None,
                "stt_model": stt_status.model if stt_status else None,
                **extra,
            }
        )

    async def start_live(
        self,
        source: str,
        emit: EventSink,
        *,
        sample_rate: int = 48_000,
        backend_capture: bool = False,
        language: str | None = "pt",
    ) -> Session:
        if source not in ("mic", "system"):
            raise SessionError(f"fonte ao vivo inválida: {source}")
        session = Session(self._new_info(source, language), emit, self.store)
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
        if self.stt:
            session.transcriber = LiveTranscriber(
                self.stt,
                session.buffer,
                language=language,
                on_segment=session.on_segment,
                on_partial=session.on_partial,
                on_language=session.on_language,
            )
            session.task = asyncio.create_task(session.transcriber.run())
        session.save()
        self._sessions[session.id] = session
        return session

    async def start_file(
        self, file_path: str, emit: EventSink, *, language: str | None = "pt"
    ) -> Session:
        # stat local de um arquivo: rápido o bastante para não valer uma thread.
        path = Path(file_path).expanduser()  # noqa: ASYNC240
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
            language,
            status="processing",
            audio_path=str(path),
            file_path=str(path),
            media_kind="video" if media.has_video else "audio",
            duration_ms=media.duration_ms,
        )
        session = Session(info, emit, self.store)
        session.save()
        self._sessions[session.id] = session
        session.task = asyncio.create_task(self._run_file(session, path, media.duration_ms))
        return session

    async def _run_file(self, session: Session, path: Path, total_ms: int | None) -> None:
        pcm = bytearray()

        async def progress(ms: int) -> None:
            await session.emit(
                SessionProgress(session_id=session.id, processed_ms=ms, total_ms=total_ms)
            )

        async def decode_progress(_ms: int) -> None:
            pass  # decodificar é ~100x mais rápido que transcrever; o progresso é o do STT

        try:
            duration = await FileDecoder(path, pcm.extend, decode_progress).run()
            session.info.duration_ms = duration
            if self.stt:
                language = await transcribe_audio(
                    self.stt,
                    pcm16_to_float32(bytes(pcm)),
                    language=session.info.language,
                    on_segment=session.on_segment,
                    on_progress=progress,
                    on_language=session.on_language,
                )
                session.info.language = language
            else:
                await progress(duration)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("falha ao processar %s", path)
            await self._finish(session, "error", error=str(exc))
            return
        await self._finish(session, "completed")

    async def stop(self, session_id: str, request_id: str | None = None) -> SessionEnded:
        session = self.get(session_id)
        if session.recorder is not None:
            # Primeiro a gravação (o ffmpeg despeja o resto do PCM no buffer), depois a
            # última passada da transcrição sobre esse resto.
            await session.recorder.stop()
            session.info.duration_ms = session.recorder.duration_ms
            if session.transcriber is not None and session.task is not None:
                session.transcriber.stop()
                with contextlib.suppress(Exception):
                    await session.task
        elif session.task is not None and not session.task.done():
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
        session.subtitles.close()
        if session.latencies_ms:
            lat = sorted(session.latencies_ms)
            log.info(
                "sessão %s: %d segmentos, latência p50=%dms p90=%dms",
                session.id,
                len(lat),
                lat[len(lat) // 2],
                lat[int(0.9 * (len(lat) - 1))],
            )
        session.info.status = "error" if reason == "error" else "completed"
        session.info.ended_at = _now()
        session.save()
        event = SessionEnded.model_validate(
            {"id": request_id, "session": session.info, "reason": reason, "error": error}
        )
        if notify:
            await session.emit(event)
        return event

    def transcript(self, session_id: str) -> list[TranscriptSegmentData]:
        if not self.store:
            return []
        return [to_segment_data(s) for s in self.store.segments(session_id)]

    async def stop_all(self, session_ids: list[str] | None = None) -> None:
        for sid in list(session_ids if session_ids is not None else self._sessions):
            if sid in self._sessions:
                with contextlib.suppress(Exception):
                    await self.stop(sid)


__all__ = ["AudioSourceError", "Session", "SessionError", "SessionManager"]
