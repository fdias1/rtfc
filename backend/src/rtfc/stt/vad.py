"""Detecção de fala (Silero VAD em ONNX, o mesmo que vem no faster-whisper; sem PyTorch)."""

from dataclasses import dataclass

from rtfc.stt.base import AudioArray

RATE = 16_000


@dataclass(frozen=True)
class SpeechSpan:
    start: int
    """Em amostras, relativo ao início do áudio analisado."""
    end: int


def speech_spans(audio: AudioArray, *, min_silence_ms: int = 400) -> list[SpeechSpan]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    if len(audio) < RATE // 10:
        return []
    opts = VadOptions(threshold=0.5, min_silence_duration_ms=min_silence_ms, speech_pad_ms=200)
    return [SpeechSpan(int(s["start"]), int(s["end"])) for s in get_speech_timestamps(audio, opts)]


def has_speech(audio: AudioArray) -> bool:
    return bool(speech_spans(audio))


def trailing_silence_s(audio: AudioArray) -> float:
    """Segundos de silêncio no fim do áudio (todo o áudio, se não houver fala)."""
    spans = speech_spans(audio)
    if not spans:
        return len(audio) / RATE
    return max(0.0, (len(audio) - spans[-1].end) / RATE)


def chunk_by_speech(audio: AudioArray, max_chunk_s: float = 28.0) -> list[tuple[int, int]]:
    """Agrupa os trechos de fala em blocos contíguos de até `max_chunk_s` (modo arquivo).

    Devolve (início, fim) em amostras. O silêncio entre blocos é pulado; dentro de um bloco
    o áudio é contíguo, então os timestamps do Whisper continuam válidos com um deslocamento.
    """
    max_len = int(max_chunk_s * RATE)
    chunks: list[tuple[int, int]] = []
    for span in speech_spans(audio, min_silence_ms=300):
        start, end = span.start, span.end
        # Fala contínua maior que um bloco: corta em pedaços fixos.
        while end - start > max_len:
            chunks.append((start, start + max_len))
            start += max_len
        if chunks and end - chunks[-1][0] <= max_len and start - chunks[-1][1] < 2 * RATE:
            chunks[-1] = (chunks[-1][0], end)
        else:
            chunks.append((start, end))
    return chunks
