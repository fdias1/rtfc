"""Transcrição de arquivos: VAD agrupa a fala em blocos de até ~28 s, transcritos em ordem."""

from collections.abc import Awaitable, Callable

from rtfc.stt.base import AudioArray, Word
from rtfc.stt.live import PROMPT_CHARS, LanguageCallback, SegmentCallback
from rtfc.stt.segmenter import split_segments
from rtfc.stt.service import SttService
from rtfc.stt.vad import chunk_by_speech

RATE = 16_000

ProgressCallback = Callable[[int], Awaitable[None]]
"""Milissegundos do arquivo já transcritos."""


async def transcribe_audio(
    stt: SttService,
    audio: AudioArray,
    *,
    language: str | None,
    on_segment: SegmentCallback,
    on_progress: ProgressCallback,
    on_language: LanguageCallback | None = None,
) -> str | None:
    """Transcreve o áudio inteiro. Devolve o idioma usado (detectado, se `language` for None)."""
    chunks = await stt.run_blocking(lambda: chunk_by_speech(audio))
    history = ""
    pending: list[Word] = []
    for start, end in chunks:
        result = await stt.transcribe(
            audio[start:end], language=language, prompt=history[-PROMPT_CHARS:] or None
        )
        if language is None and result.language:
            language = result.language
            if on_language:
                await on_language(language)
        pending.extend(w.shifted(start / RATE) for w in result.words if w.text.strip())
        segments, pending = split_segments(pending, final=False)
        for seg in segments:
            history = (history + " " + seg.text).strip()
            await on_segment(seg, 0.0)
        await on_progress(end * 1000 // RATE)
    segments, _ = split_segments(pending, final=True)
    for seg in segments:
        await on_segment(seg, 0.0)
    await on_progress(len(audio) * 1000 // RATE)
    return language
