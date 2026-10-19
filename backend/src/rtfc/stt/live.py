"""Transcrição em streaming com a política LocalAgreement (como no whisper_streaming).

A cada ~1 s o trecho ainda não fechado (do fim do último segmento até agora) é
retranscrito. Uma palavra só é **confirmada** quando duas passadas seguidas concordam
nela; o resto é texto **provisório**. Pausas detectadas pelo VAD confirmam tudo na hora,
o que derruba a latência no fim das frases.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

from rtfc.audio.ring_buffer import PcmRingBuffer
from rtfc.stt.base import Word, pcm16_to_float32
from rtfc.stt.segmenter import Segment, split_segments
from rtfc.stt.service import SttService
from rtfc.stt.vad import trailing_silence_s

log = logging.getLogger(__name__)

RATE = 16_000

STEP_S = 1.0
MIN_AUDIO_S = 0.6
PAUSE_CONFIRM_S = 0.7
MAX_WINDOW_S = 20.0
PROMPT_CHARS = 200

SegmentCallback = Callable[[Segment, float], Awaitable[None]]
"""(segmento fechado, latência em segundos entre o fim da fala e a confirmação)."""
PartialCallback = Callable[[float, str, str], Awaitable[None]]
"""(início do trecho aberto em s, texto confirmado, texto provisório)."""
LanguageCallback = Callable[[str], Awaitable[None]]


def _norm(word: Word) -> str:
    return re.sub(r"[^\w]", "", word.text.lower())


def common_prefix(a: list[Word], b: list[Word]) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if _norm(x) != _norm(y):
            break
        n += 1
    return n


def _text(words: list[Word]) -> str:
    return "".join(w.text for w in words).strip()


class LiveTranscriber:
    def __init__(
        self,
        stt: SttService,
        buffer: PcmRingBuffer,
        *,
        language: str | None,
        on_segment: SegmentCallback,
        on_partial: PartialCallback,
        on_language: LanguageCallback | None = None,
    ) -> None:
        self._stt = stt
        self._buffer = buffer
        self.language = language
        self._on_segment = on_segment
        self._on_partial = on_partial
        self._on_language = on_language
        self._stop = asyncio.Event()

        self.window_start = 0
        """Amostra absoluta onde começa o trecho aberto."""
        self.confirmed: list[Word] = []
        """Palavras confirmadas que ainda não fecharam um segmento."""
        self.tentative: list[Word] = []
        self.history = ""
        self.segments_emitted = 0
        self._last_partial: tuple[str, str] = ("", "")

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            t0 = loop.time()
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("passo de transcrição falhou")
            remaining = STEP_S - (loop.time() - t0)
            if remaining > 0:
                try:
                    await asyncio.wait_for(self._stop.wait(), remaining)
                except TimeoutError:
                    pass
        await self.step(final=True)

    async def step(self, *, final: bool = False) -> None:
        read = self._buffer.read_since(self.window_start)
        if read.dropped_samples:
            log.warning("transcrição atrasada: %d amostras descartadas", read.dropped_samples)
            self.window_start = read.start_sample
            self.tentative = []
        audio = pcm16_to_float32(read.data)
        offset = read.start_sample / RATE
        now = offset + len(audio) / RATE
        if len(audio) < MIN_AUDIO_S * RATE and not (final and len(audio) > 0):
            return

        silence = await self._stt.run_blocking(lambda: trailing_silence_s(audio))
        if silence >= len(audio) / RATE - 0.05:
            # Só silêncio no trecho aberto: fecha o que houver e pula o silêncio.
            await self._commit(self.tentative, final=True, now=now)
            self.window_start = max(self.window_start, int((now - 0.2) * RATE))
            await self._partial()
            return

        result = await self._stt.transcribe(
            audio, language=self.language, prompt=self.history[-PROMPT_CHARS:] or None
        )
        if self.language is None and result.language:
            self.language = result.language
            if self._on_language:
                await self._on_language(result.language)

        cutoff = self.confirmed[-1].end if self.confirmed else offset
        hyp = [w.shifted(offset) for w in result.words if w.text.strip()]
        hyp = [w for w in hyp if w.start >= cutoff - 0.05]

        paused = silence >= PAUSE_CONFIRM_S
        if final or paused:
            agreed, rest = hyp, []
        else:
            n = common_prefix(self.tentative, hyp)
            agreed, rest = hyp[:n], hyp[n:]
        self.tentative = rest
        await self._commit(agreed, final=final or (paused and not rest), now=now)

        # Trecho aberto longo demais (fala sem pausa nem pontuação): fecha à força.
        if now - self.window_start / RATE > MAX_WINDOW_S:
            if self.confirmed or self.tentative:
                await self._commit(self.tentative, final=True, now=now)
            else:
                self.window_start = int((now - 5.0) * RATE)
        await self._partial()

    async def _commit(self, words: list[Word], *, final: bool, now: float) -> None:
        if words is self.tentative:
            words = list(words)
            self.tentative = []
        self.confirmed.extend(words)
        segments, self.confirmed = split_segments(self.confirmed, final=final)
        for seg in segments:
            self.segments_emitted += 1
            self.history = (self.history + " " + seg.text).strip()
            await self._on_segment(seg, max(0.0, now - seg.end))
        if segments:
            self.window_start = max(self.window_start, int(segments[-1].end * RATE))

    async def _partial(self) -> None:
        current = (_text(self.confirmed), _text(self.tentative))
        if current == self._last_partial:
            return
        self._last_partial = current
        words = self.confirmed or self.tentative
        start = words[0].start if words else self.window_start / RATE
        await self._on_partial(start, *current)
