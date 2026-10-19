"""LocalAgreement, segmentação e silêncio, com um STT falso guiado por uma "linha do tempo"."""

import pytest

from rtfc.audio.ring_buffer import PcmRingBuffer
from rtfc.stt import live
from rtfc.stt.base import AudioArray, Transcription, Word
from rtfc.stt.live import LiveTranscriber, common_prefix
from rtfc.stt.segmenter import Segment, split_segments
from rtfc.stt.service import SttService

RATE = 16_000

# (palavra, início, fim) em segundos absolutos da sessão.
SPEECH = [
    (" A", 0.2, 0.4),
    (" inflação", 0.4, 0.9),
    (" caiu.", 0.9, 1.4),
    (" O", 2.6, 2.8),
    (" desemprego", 2.8, 3.4),
    (" subiu", 3.4, 3.9),
    (" muito.", 3.9, 4.5),
]


class TimelineStt(SttService):
    """Devolve as palavras da linha do tempo que cabem no áudio recebido.

    Simula o Whisper "mudando de ideia": a última palavra ainda incompleta vem trocada.
    """

    def __init__(self) -> None:
        super().__init__(download_models=False)
        self.transcriber: LiveTranscriber | None = None
        self.calls = 0

    async def transcribe(
        self, audio: AudioArray, *, language: str | None, prompt: str | None
    ) -> Transcription:
        self.calls += 1
        assert self.transcriber is not None
        offset = self.transcriber.window_start / RATE
        end = offset + len(audio) / RATE
        words = []
        for text, s, e in SPEECH:
            if s >= offset - 0.01 and s < end:
                if e > end:
                    text = " ???"  # palavra cortada: hipótese instável
                words.append(Word(text, s - offset, min(e, end) - offset))
        return Transcription(words, language or "pt")

    async def run_blocking(self, fn):  # type: ignore[no-untyped-def,override]
        return fn()


def silence_after_speech(audio: AudioArray) -> float:
    """VAD falso: silêncio = tempo desde o fim da última palavra da linha do tempo."""
    assert _current is not None
    offset = _current.window_start / RATE
    end = offset + len(audio) / RATE
    spoken = [e for _, s, e in SPEECH if offset - 0.01 <= s < end]
    if not spoken:
        return len(audio) / RATE
    return max(0.0, end - min(max(spoken), end))


_current: LiveTranscriber | None = None


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    global _current
    monkeypatch.setattr(live, "trailing_silence_s", silence_after_speech)
    stt = TimelineStt()
    buffer = PcmRingBuffer()
    segments: list[tuple[Segment, float]] = []
    partials: list[tuple[str, str]] = []

    async def on_segment(seg: Segment, latency: float) -> None:
        segments.append((seg, latency))

    async def on_partial(_start: float, confirmed: str, tentative: str) -> None:
        partials.append((confirmed, tentative))

    t = LiveTranscriber(stt, buffer, language="pt", on_segment=on_segment, on_partial=on_partial)
    stt.transcriber = t
    _current = t
    yield t, buffer, segments, partials
    _current = None


async def feed(t: LiveTranscriber, buffer: PcmRingBuffer, seconds: float) -> None:
    """Empurra áudio em passos de 0,5 s, rodando um passo de transcrição a cada passo."""
    for _ in range(int(seconds / 0.5)):
        buffer.write(b"\x00\x00" * (RATE // 2))
        await t.step()


async def test_words_confirmed_by_agreement_and_split_at_sentence_end(harness) -> None:  # type: ignore[no-untyped-def]
    t, buffer, segments, partials = harness
    await feed(t, buffer, 6.0)
    texts = [s.text for s, _ in segments]
    assert texts == ["A inflação caiu.", "O desemprego subiu muito."]
    # Palavras cortadas ("???") nunca chegam a um segmento confirmado.
    assert all("???" not in s.text for s, _ in segments)
    # Algum parcial mostrou texto provisório antes da confirmação.
    assert any(tent for _, tent in partials)
    # Latência (fim da fala → confirmação) dentro da meta do PRD.
    assert max(lat for _, lat in segments) <= 3.0


async def test_final_step_flushes_open_words(harness) -> None:  # type: ignore[no-untyped-def]
    t, buffer, segments, _ = harness
    buffer.write(b"\x00\x00" * int(3.5 * RATE))  # para no meio da 2ª frase
    await t.step()
    await t.step(final=True)
    assert [s.text for s, _ in segments][-1].startswith("O desemprego")


def test_common_prefix_ignores_case_and_punctuation() -> None:
    a = [Word(" Caiu", 0, 1), Word(" muito", 1, 2)]
    b = [Word(" caiu.", 0, 1), Word(" pouco", 1, 2)]
    assert common_prefix(a, b) == 1


def test_split_segments_by_pause_and_length() -> None:
    words = [Word(" um", 0.0, 0.5), Word(" dois", 2.0, 2.5), Word(" três", 2.5, 3.0)]
    closed, rest = split_segments(words, final=False)
    assert [s.text for s in closed] == ["um"]
    assert [w.text for w in rest] == [" dois", " três"]
    long_words = [Word(f" w{i}", i * 0.9, i * 0.9 + 0.8) for i in range(20)]
    closed, _ = split_segments(long_words, final=True)
    assert all(s.end - s.start <= 15.0 for s in closed)
