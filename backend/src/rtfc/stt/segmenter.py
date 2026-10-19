"""Regras de corte das palavras confirmadas em segmentos (as "frases" da transcrição e do SRT)."""

import re
from dataclasses import dataclass

from rtfc.stt.base import Word

SENTENCE_END = re.compile(r"[.!?…]['\"”»)]*$")

MAX_SEGMENT_S = 15.0
"""Segmento longo demais vira legenda ilegível; corta mesmo sem pontuação."""
PAUSE_SPLIT_S = 1.0
"""Pausa entre duas palavras que, sozinha, separa segmentos."""


@dataclass(frozen=True)
class Segment:
    words: tuple[Word, ...]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return "".join(w.text for w in self.words).strip()


def ends_sentence(word: Word) -> bool:
    return bool(SENTENCE_END.search(word.text.strip()))


def split_segments(words: list[Word], *, final: bool) -> tuple[list[Segment], list[Word]]:
    """Separa `words` em segmentos fechados e o resto ainda aberto.

    Fecha um segmento ao fim de uma frase, numa pausa longa ou ao passar de MAX_SEGMENT_S.
    Com `final=True` o resto também vira segmento (fim da sessão ou do arquivo).
    """
    segments: list[Segment] = []
    current: list[Word] = []
    for word in words:
        if current and (
            word.start - current[-1].end >= PAUSE_SPLIT_S
            or word.end - current[0].start > MAX_SEGMENT_S
        ):
            segments.append(Segment(tuple(current)))
            current = []
        current.append(word)
        if ends_sentence(word):
            segments.append(Segment(tuple(current)))
            current = []
    if final and current:
        segments.append(Segment(tuple(current)))
        current = []
    return segments, current
