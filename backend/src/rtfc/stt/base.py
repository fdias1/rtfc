"""Interface comum dos motores de transcrição (STT).

Os motores só sabem transcrever um trecho curto (≤ 30 s) de áudio float32 16 kHz com
timestamps por palavra. Streaming, segmentação e arquivos longos ficam em `rtfc.stt.live`
e `rtfc.stt.files`, iguais para qualquer motor.
"""

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import numpy.typing as npt

AudioArray = npt.NDArray[np.float32]

MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")


@dataclass(frozen=True)
class Word:
    text: str
    """Como o Whisper devolve: normalmente com o espaço inicial (" palavra")."""
    start: float
    """Segundos, relativos ao início do trecho transcrito (ou da sessão, depois de deslocado)."""
    end: float
    prob: float = 1.0

    def shifted(self, offset: float) -> "Word":
        return Word(self.text, self.start + offset, self.end + offset, self.prob)


@dataclass(frozen=True)
class Transcription:
    words: list[Word] = field(default_factory=list)
    language: str | None = None
    language_prob: float | None = None

    @property
    def text(self) -> str:
        return "".join(w.text for w in self.words).strip()


class STTEngine(Protocol):
    name: str
    model: str

    def load(self) -> None:
        """Carrega (e baixa, se preciso) o modelo. Pode demorar; chamar fora do event loop."""

    def transcribe(
        self, audio: AudioArray, *, language: str | None = None, prompt: str | None = None
    ) -> Transcription:
        """Transcreve um trecho curto. `language=None` detecta o idioma. Bloqueante."""
        ...


def pcm16_to_float32(pcm: bytes) -> AudioArray:
    return (np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0).astype(np.float32)
