"""Sessões: cada uma é uma pasta com `session.json`, `audio.ogg` (ao vivo) e as legendas.

Uma sessão junta a fonte de áudio (gravação ao vivo ou arquivo), a transcrição e a
persistência (SQLite + SRT/VTT), e emite os eventos do protocolo para a conexão dona.
"""

import asyncio
import contextlib
import logging
import os
import re
import secrets
import shutil
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from rtfc.audio import ffmpeg
from rtfc.audio.ring_buffer import PcmRingBuffer
from rtfc.audio.sources import AudioSourceError, FileDecoder, LiveRecorder
from rtfc.claims import Anchor, ClaimPipeline, manual_claim, to_claim_data
from rtfc.claims.extractor import generate_context
from rtfc.config import SecretStore, SettingsStore
from rtfc.diarization import MIN_EMBED_S, DiarizationService, speaker_label
from rtfc.diarization.session import Changes, SessionDiarizer
from rtfc.factcheck.review import ReviewService
from rtfc.factcheck.service import PRIORITY_MANUAL, CheckContext, CheckService
from rtfc.llm import LlmClient, LlmError
from rtfc.protocol import (
    ClaimData,
    SessionEnded,
    SessionInfo,
    SessionListItem,
    SessionProgress,
    SessionUpdated,
    SpeakerAssignment,
    SpeakersUpdated,
    TranscriptPartial,
    TranscriptSegment,
    TranscriptSegmentData,
    TranscriptWord,
)
from rtfc.storage import (
    CheckStore,
    ClaimStore,
    StoredClaim,
    StoredSegment,
    StoredWord,
    SubtitleWriter,
    TranscriptStore,
    rewrite_subtitles,
)
from rtfc.stt.base import AudioArray, pcm16_to_float32
from rtfc.stt.files import transcribe_audio
from rtfc.stt.live import LiveTranscriber
from rtfc.stt.segmenter import Segment
from rtfc.stt.service import SttService

log = logging.getLogger(__name__)

EventSink = Callable[[BaseModel], Awaitable[None]]

LIVE_PROGRESS_EVERY_MS = 1000
RATE = 16_000
SESSION_ID_RE = re.compile(r"\d{8}-\d{6}-(mic|system|file)-[0-9a-f]{4}")


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
        self.claims: ClaimPipeline | None = None
        self.task: asyncio.Task[None] | None = None
        self.subtitles = SubtitleWriter(Path(info.dir))
        self.clock_start = time.monotonic()
        """Relógio do áudio ao vivo: o instante t (ms) da gravação ≈ clock_start + t."""
        self.segment_count = 0
        self.latencies_ms: list[int] = []
        self._last_progress_ms = 0
        self.diarizer: SessionDiarizer | None = None
        self.on_relabel: Callable[[Changes], Awaitable[None]] | None = None
        self.file_pcm: bytearray | None = None
        """PCM 16 kHz do arquivo inteiro (sessões de arquivo), para a diarização."""

    @property
    def id(self) -> str:
        return self.info.id

    def save(self) -> None:
        self.write_info(self.info)

    @staticmethod
    def write_info(info: SessionInfo) -> None:
        path = Path(info.dir) / "session.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(info.model_dump_json(indent=2), encoding="utf-8")
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

    def segment_audio(self, start_s: float, end_s: float) -> AudioArray | None:
        a, b = int(start_s * RATE), int(end_s * RATE)
        if self.file_pcm is not None:
            return pcm16_to_float32(bytes(self.file_pcm[a * 2 : b * 2]))
        read = self.buffer.read_since(a)
        if read.start_sample > a:
            return None  # já saiu do buffer
        return pcm16_to_float32(read.data[: (b - a) * 2])

    async def on_segment(self, seg: Segment, latency_s: float) -> None:
        index = self.segment_count
        self.segment_count += 1
        speaker: str | None = None
        changes: Changes = {}
        if self.diarizer:
            speaker, changes = await self.diarizer.assign(
                index, self.segment_audio(seg.start, seg.end)
            )
        stored = StoredSegment(
            index=index,
            start_ms=round(seg.start * 1000),
            end_ms=round(seg.end * 1000),
            text=seg.text,
            words=tuple(
                StoredWord(round(w.start * 1000), round(w.end * 1000), w.text.strip(), w.prob)
                for w in seg.words
            ),
            speaker=speaker,
        )
        if self._store:
            self._store.add_segment(self.id, stored)
        self.subtitles.add(
            stored.start_ms, stored.end_ms, stored.text, speaker_label(speaker, self.info.speakers)
        )
        live = self.info.source != "file"
        latency_ms = round(latency_s * 1000) if live else None
        if latency_ms is not None:
            self.latencies_ms.append(latency_ms)
        await self.emit(
            TranscriptSegment(
                session_id=self.id, segment=to_segment_data(stored), latency_ms=latency_ms
            )
        )
        if self.claims:
            self.claims.submit(stored)
        if changes and self.on_relabel:
            await self.on_relabel(changes)

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
        settings: SettingsStore | None = None,
        secrets: SecretStore | None = None,
        diarization: DiarizationService | None = None,
    ) -> None:
        self.diarization = diarization
        self.sessions_dir = sessions_dir or default_sessions_dir()
        self.stt = stt
        self.store = store
        self.settings = settings
        self.secrets = secrets
        self.claim_store = ClaimStore(store.db) if store else None
        self._sessions: dict[str, Session] = {}
        self._listeners: set[EventSink] = set()
        self.checks: CheckService | None = None
        self.review: ReviewService | None = None
        if store and self.claim_store and settings and secrets:
            self.check_store = CheckStore(store.db)
            stale = self.claim_store.interrupt_pending()
            if stale:
                log.info(
                    "%d checagens pendentes de uma execução anterior marcadas como canceladas",
                    stale,
                )
            self.checks = CheckService(
                claims=self.claim_store,
                checks=self.check_store,
                settings=settings,
                secrets=secrets,
                broadcast=self.broadcast,
                session_context=self._session_context,
                speech_age=self.speech_age_ms,
            )
            self.review = ReviewService(
                claims=self.claim_store,
                checks=self.check_store,
                check_service=self.checks,
                settings=settings,
                secrets=secrets,
                broadcast=self.broadcast,
                session_context=self._session_context,
                stt=stt,
            )

    # --- Eventos para todas as conexões ----------------------------------------

    def add_listener(self, sink: EventSink) -> None:
        self._listeners.add(sink)

    def remove_listener(self, sink: EventSink) -> None:
        self._listeners.discard(sink)

    async def broadcast(self, event: BaseModel) -> None:
        for sink in list(self._listeners):
            with contextlib.suppress(Exception):
                await sink(event)

    def speech_age_ms(self, session_id: str, end_ms: int) -> int | None:
        """Quanto tempo passou desde que o trecho foi falado (só em sessões ao vivo ativas)."""
        session = self._sessions.get(session_id)
        if session is None or session.info.source == "file":
            return None
        return round((time.monotonic() - session.clock_start) * 1000) - end_ms

    def _session_context(self, session_id: str, start_ms: int, end_ms: int) -> CheckContext:
        """Tudo que a checagem precisa saber além da afirmação (ADR 0006)."""
        try:
            info = self.load_info(session_id)
        except (SessionError, ValueError):
            return CheckContext(language=None, when=date.today())
        segments = self._segments(session_id)
        around = [
            s for s in segments if s.end_ms >= start_ms - 60_000 and s.start_ms <= end_ms + 15_000
        ]
        transcript = "\n".join(
            f"{'>> ' if s.start_ms <= end_ms and s.end_ms >= start_ms else ''}"
            f"{f'({who}) ' if (who := speaker_label(s.speaker, info.speakers)) else ''}{s.text}"
            for s in around
        )
        return CheckContext(
            language=info.language,
            when=datetime.fromisoformat(info.started_at).date(),
            content=info.context,
            transcript=transcript,
            speakers=info.speakers,
        )

    # --- Contexto do conteúdo ---------------------------------------------------

    async def _apply_context(self, session_id: str, text: str | None, source: str) -> SessionInfo:
        info = self.load_info(session_id)
        text = (text or "").strip() or None
        info.context = text
        info.context_source = source if text else None  # type: ignore[assignment]
        Session.write_info(info)
        await self.broadcast(SessionUpdated(session=info))
        return info

    async def set_context(self, session_id: str, text: str | None) -> SessionInfo:
        if text and text.strip():
            return await self._apply_context(session_id, text, "user")
        # Vazio: volta para o automático (regerado a partir da transcrição).
        await self._apply_context(session_id, None, "auto")
        return await self.generate_context(session_id)

    async def generate_context(self, session_id: str) -> SessionInfo:
        info = self.load_info(session_id)
        segments = self._segments(session_id)
        if not segments:
            raise SessionError("ainda não há transcrição para gerar o contexto")
        try:
            result = await generate_context(
                self.extractor_client(),
                segments=segments,
                language=info.language,
                when=datetime.fromisoformat(info.started_at).date(),
                speakers=info.speakers,
            )
        except (LlmError, ValueError) as exc:
            raise SessionError(f"não foi possível gerar o contexto: {exc}") from exc
        return await self._apply_context(session_id, result.value.context, "auto")

    def _live_sessions(self, *, but: str | None = None) -> list[Session]:
        return [s for sid, s in self._sessions.items() if sid != but and s.info.source != "file"]

    def claim_data(self, claim: StoredClaim) -> ClaimData:
        if self.checks:
            return self.checks.data(claim)  # type: ignore[return-value]
        return to_claim_data(claim)

    def _auto_check(self, claim: StoredClaim) -> None:
        settings = self.settings.settings if self.settings else None
        if self.checks and settings and settings.auto_check and claim.dedup_of is None:
            asyncio.get_running_loop().create_task(self.checks.enqueue(claim))

    def extractor_client(self) -> LlmClient:
        if not (self.settings and self.secrets):
            raise SessionError("extração de afirmações não configurada")
        return LlmClient(self.settings.settings.extractor, self.secrets)

    def _attach_claims(self, session: Session) -> None:
        if not (self.settings and self.secrets and self.claim_store):
            return
        if not self.settings.settings.auto_extract:
            return
        session.claims = ClaimPipeline(
            session.id,
            client_factory=self.extractor_client,
            store=self.claim_store,
            emit=session.emit,
            language=lambda: session.info.language,
            on_claim=self._auto_check,
            content_context=lambda: session.info.context,
            min_score=lambda: self.settings.settings.min_claim_score if self.settings else 1,
            on_auto_context=lambda text: self._apply_context(session.id, text, "auto"),
            auto_context_allowed=lambda: session.info.context_source != "user",
            speakers=lambda: session.info.speakers,
        )
        session.claims.start()

    def _attach_diarizer(self, session: Session) -> None:
        settings = self.settings.settings if self.settings else None
        if self.diarization is None or settings is None or not settings.diarization:
            return
        session.diarizer = SessionDiarizer(
            self.diarization, settings.speaker_threshold, wait_model=session.info.source == "file"
        )
        self.diarization.warm_up()

        async def relabel(changes: Changes) -> None:
            await self._apply_speakers(session.id, changes)

        session.on_relabel = relabel

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionError(f"sessão desconhecida: {session_id}") from None

    def _new_info(
        self, source: str, language: str | None, context: str | None = None, **extra: object
    ) -> SessionInfo:
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
                "context": (context or "").strip() or None,
                "context_source": "user" if (context or "").strip() else None,
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
        context: str | None = None,
    ) -> Session:
        if source not in ("mic", "system"):
            raise SessionError(f"fonte ao vivo inválida: {source}")
        if self.review:
            # A revisão usa um modelo grande: ao vivo a memória volta para o Whisper.
            await self.review.pause()
        session = Session(self._new_info(source, language, context), emit, self.store)
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
            self._attach_claims(session)
            self._attach_diarizer(session)
        session.save()
        self._sessions[session.id] = session
        return session

    async def start_file(
        self,
        file_path: str,
        emit: EventSink,
        *,
        language: str | None = "pt",
        context: str | None = None,
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
            context,
            status="processing",
            audio_path=str(path),
            file_path=str(path),
            media_kind="video" if media.has_video else "audio",
            duration_ms=media.duration_ms,
        )
        session = Session(info, emit, self.store)
        session.save()
        self._sessions[session.id] = session
        if self.stt:
            self._attach_claims(session)
            self._attach_diarizer(session)
        session.task = asyncio.create_task(self._run_file(session, path, media.duration_ms))
        return session

    async def _run_file(self, session: Session, path: Path, total_ms: int | None) -> None:
        pcm = bytearray()
        if session.diarizer:
            session.file_pcm = pcm

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
                if session.claims:
                    await session.claims.close()
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
            if session.claims:
                # As últimas frases ainda passam pelo extrator.
                await session.claims.close()
        elif session.task is not None and not session.task.done():
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
            if session.claims:
                session.claims.cancel()
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
        session.subtitles.close()
        if session.diarizer and reason != "error":
            # Com a sessão inteira, corrige as decisões precoces do modo ao vivo (ADR 0008).
            changes = session.diarizer.refine()
            if changes:
                log.info("sessão %s: refinamento mudou o falante de %d segmentos", session.id,
                         len(changes))  # fmt: skip
                await self._apply_speakers(session.id, changes)
            self._rewrite_subtitles(session.id, session.info)
        session.file_pcm = None
        self._sessions.pop(session.id, None)
        if session.latencies_ms:
            lat = sorted(session.latencies_ms)
            log.info(
                "sessão %s: %d segmentos, latência p50=%dms p90=%dms",
                session.id,
                len(lat),
                lat[len(lat) // 2],
                lat[int(0.9 * (len(lat) - 1))],
            )
        if (
            self.review
            and session.info.source != "file"
            and not self._live_sessions(but=session.id)
        ):
            await self.review.resume()
        if (
            self.review
            and self.settings
            and self.settings.settings.auto_review
            and reason != "error"
            and self.claim_store
            and self.claim_store.for_session(session.id)
        ):
            await self.review.start(session.id, "pending")
        if session.claims and session.claims.latencies_ms:
            lat = sorted(session.claims.latencies_ms)
            log.info(
                "sessão %s: %d afirmações, latência da extração p50=%dms p90=%dms",
                session.id,
                len(lat),
                lat[len(lat) // 2],
                lat[int(0.9 * (len(lat) - 1))],
            )
        if reason == "error":
            session.info.status = "error"
        elif reason == "stopped" and session.info.source == "file":
            # Arquivo cancelado no meio: a transcrição ficou incompleta.
            session.info.status = "interrupted"
        else:
            session.info.status = "completed"
        session.info.ended_at = _now()
        session.save()
        event = SessionEnded.model_validate(
            {"id": request_id, "session": session.info, "reason": reason, "error": error}
        )
        if notify:
            await session.emit(event)
        return event

    # --- Falantes (M4) -----------------------------------------------------------

    async def _apply_speakers(
        self, session_id: str, changes: Changes, request_id: str | None = None
    ) -> SpeakersUpdated:
        if self.store:
            self.store.set_speakers(session_id, changes)
        active = self._sessions.get(session_id)
        if active and active.claims:
            active.claims.relabel(changes)
        if self.claim_store:
            for claim in self.claim_store.set_speakers(session_id, changes):
                if self.checks:
                    await self.checks.emit(claim)
        event = SpeakersUpdated(
            id=request_id,
            session_id=session_id,
            segments=[SpeakerAssignment(index=i, speaker=sp) for i, sp in sorted(changes.items())],
        )
        await self.broadcast(event)
        return event

    def _rewrite_subtitles(self, session_id: str, info: SessionInfo) -> None:
        if not self.store:
            return
        cues = [
            (s.start_ms, s.end_ms, s.text, speaker_label(s.speaker, info.speakers))
            for s in self.store.segments(session_id)
        ]
        try:
            rewrite_subtitles(Path(info.dir), cues)
        except OSError:
            log.exception("não foi possível regravar as legendas de %s", session_id)

    async def rename_speaker(self, session_id: str, speaker: str, name: str | None) -> SessionInfo:
        info = self.load_info(session_id)
        name = (name or "").strip()
        speakers = dict(info.speakers)
        if name:
            speakers[speaker] = name
        else:
            speakers.pop(speaker, None)
        info.speakers = speakers
        Session.write_info(info)
        if session_id not in self._sessions:
            # Ao vivo, as legendas são regravadas no fim da sessão.
            await asyncio.to_thread(self._rewrite_subtitles, session_id, info)
        await self.broadcast(SessionUpdated(session=info))
        return info

    async def refine_speakers(
        self, session_id: str, request_id: str | None = None
    ) -> SpeakersUpdated:
        """Refaz os falantes de uma sessão salva a partir do áudio (botão "Refinar falantes")."""
        if session_id in self._sessions:
            raise SessionError("encerre a sessão antes de refinar os falantes")
        if self.diarization is None or not self.store:
            raise SessionError("diarização indisponível")
        info = self.load_info(session_id)
        segments = self.store.segments(session_id)
        if not segments:
            raise SessionError("a sessão não tem transcrição")
        pcm = bytearray()

        async def ignore(_ms: int) -> None:
            pass

        try:
            await FileDecoder(Path(info.audio_path), pcm.extend, ignore).run()
        except (OSError, AudioSourceError, ffmpeg.FfmpegNotFoundError) as exc:
            raise SessionError(f"não foi possível ler o áudio: {exc}") from exc
        threshold = self.settings.settings.speaker_threshold if self.settings else 0.6
        diarizer = SessionDiarizer(self.diarization, threshold)
        chunks = [
            pcm16_to_float32(
                bytes(pcm[s.start_ms * RATE // 1000 * 2 : s.end_ms * RATE // 1000 * 2])
            )
            for s in segments
        ]
        embeddings = await self.diarization.embed_many(chunks)
        if all(e is None for e in embeddings):
            raise SessionError("não foi possível analisar as vozes (modelo indisponível?)")
        for s, emb, chunk in zip(segments, embeddings, chunks, strict=True):
            diarizer.embeddings[s.index] = emb
            diarizer.durations[s.index] = len(chunk) / RATE
            diarizer.reliable[s.index] = emb is not None and len(chunk) / RATE >= MIN_EMBED_S
            diarizer.labels[s.index] = s.speaker
        changes = diarizer.refine()
        event = await self._apply_speakers(session_id, changes, request_id)
        await asyncio.to_thread(self._rewrite_subtitles, session_id, info)
        return event

    # --- Sessões salvas -------------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        # IDs são gerados por nós; qualquer outra coisa (/, ..) é recusada.
        if not SESSION_ID_RE.fullmatch(session_id):
            raise SessionError(f"id de sessão inválido: {session_id}")
        path = self.sessions_dir / session_id
        if not (path / "session.json").is_file():
            raise SessionError(f"sessão não encontrada: {session_id}")
        return path

    def load_info(self, session_id: str) -> SessionInfo:
        if session_id in self._sessions:
            return self._sessions[session_id].info
        path = self._session_dir(session_id) / "session.json"
        return SessionInfo.model_validate_json(path.read_text(encoding="utf-8"))

    def _list_sync(self) -> list[SessionListItem]:
        items: list[SessionListItem] = []
        if not self.sessions_dir.is_dir():
            return items
        for child in self.sessions_dir.iterdir():
            meta = child / "session.json"
            if not (SESSION_ID_RE.fullmatch(child.name) and meta.is_file()):
                continue
            try:
                info = SessionInfo.model_validate_json(meta.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("session.json inválido em %s", child)
                continue
            if child.name in self._sessions:
                info = self._sessions[child.name].info
            elif info.status in ("recording", "processing"):
                # Ficou "em andamento" sem estar ativa: o app caiu no meio. Corrige no disco.
                info.status = "interrupted"
                Session.write_info(info)
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            count = self.store.segment_count(info.id) if self.store else 0
            items.append(SessionListItem(session=info, size_bytes=size, segment_count=count))
        items.sort(key=lambda i: i.session.started_at, reverse=True)
        return items

    async def list_sessions(self) -> list[SessionListItem]:
        return await asyncio.to_thread(self._list_sync)

    async def rename(self, session_id: str, title: str | None) -> SessionInfo:
        info = self.load_info(session_id)
        info.title = (title or "").strip() or None
        Session.write_info(info)
        return info

    async def delete(self, session_id: str) -> None:
        if session_id in self._sessions:
            raise SessionError("encerre a sessão antes de apagá-la")
        if self.review:
            await self.review.cancel(session_id)
        path = self._session_dir(session_id)
        await asyncio.to_thread(shutil.rmtree, path)
        if self.store:
            self.store.delete_session(session_id)
        if self.claim_store:
            ids = [c.id for c in self.claim_store.for_session(session_id)]
            self.claim_store.delete_session(session_id)
            if self.checks:
                self.check_store.delete(ids)

    # --- Afirmações -------------------------------------------------------------

    def claims(self, session_id: str) -> list[ClaimData]:
        if not self.claim_store:
            return []
        return [self.claim_data(c) for c in self.claim_store.for_session(session_id)]

    def _segments(self, session_id: str) -> list[StoredSegment]:
        active = self._sessions.get(session_id)
        if active and active.claims:
            return active.claims.segments
        return self.store.segments(session_id) if self.store else []

    async def manual_claim(
        self, session_id: str, from_seg: int, from_word: int, to_seg: int, to_word: int
    ) -> StoredClaim:
        if not self.claim_store:
            raise SessionError("afirmações indisponíveis")
        info = self.load_info(session_id)
        segments = self._segments(session_id)
        by_index = {s.index: s for s in segments}
        first, last = by_index.get(from_seg), by_index.get(to_seg)
        if not first or not last or (from_seg, from_word) > (to_seg, to_word):
            raise SessionError("trecho inválido")
        try:
            start_ms = first.words[from_word].start_ms
            end_ms = last.words[to_word].end_ms
        except IndexError:
            raise SessionError("trecho inválido") from None
        where = Anchor(from_seg, from_word, to_seg, to_word, start_ms, end_ms)
        try:
            claim = await manual_claim(
                session_id,
                segments,
                where,
                client=self.extractor_client(),
                store=self.claim_store,
                language=info.language,
                when=datetime.fromisoformat(info.started_at).date(),
                content_context=info.context,
                speakers=info.speakers,
            )
        except (LlmError, ValueError) as exc:
            raise SessionError(f"não foi possível preparar o trecho: {exc}") from exc
        if self.checks and claim.dedup_of is None:
            # Pedido explícito do usuário: fura a fila, mesmo com a checagem automática desligada.
            claim = await self.checks.enqueue(claim, priority=PRIORITY_MANUAL)
        return claim

    async def discard_claim(self, claim_id: str) -> StoredClaim:
        if not self.claim_store:
            raise SessionError("afirmações indisponíveis")
        claim = self.claim_store.get(claim_id)
        if claim is None:
            raise SessionError(f"afirmação desconhecida: {claim_id}")
        if self.checks and claim.status in ("queued", "checking"):
            await self.checks.cancel(claim_id)
        claim = claim.with_status("discarded")
        self.claim_store.upsert(claim)
        return claim

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
