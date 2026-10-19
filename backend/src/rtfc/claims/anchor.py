"""Localiza o `source_text` devolvido pelo LLM nas palavras da transcrição.

O modelo às vezes muda uma vírgula ou um acento ao copiar; por isso a busca é aproximada
(janela de palavras com maior similaridade), restrita aos segmentos indicados.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from rtfc.storage import StoredSegment

MIN_SIMILARITY = 0.6


@dataclass(frozen=True)
class Anchor:
    from_segment: int
    from_word: int
    to_segment: int
    to_word: int
    start_ms: int
    end_ms: int


def normalize_token(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w]", "", text)


def _tokens(text: str) -> list[str]:
    return [t for t in (normalize_token(w) for w in text.split()) if t]


def anchor(source_text: str, segments: list[StoredSegment]) -> Anchor | None:
    """Melhor janela contígua de palavras (pode cruzar segmentos) parecida com `source_text`."""
    target = _tokens(source_text)
    words = [(seg, i, normalize_token(w.text)) for seg in segments for i, w in enumerate(seg.words)]
    words = [w for w in words if w[2]]
    if not target or not words:
        return None

    n = len(target)
    best: tuple[float, int, int] | None = None
    for size in {max(1, n - 2), n, n + 2}:
        for start in range(0, max(1, len(words) - size + 1)):
            window = [w[2] for w in words[start : start + size]]
            score = SequenceMatcher(None, target, window, autojunk=False).ratio()
            if best is None or score > best[0]:
                best = (score, start, min(start + size, len(words)) - 1)
    if best is None or best[0] < MIN_SIMILARITY:
        return None
    _, i, j = best
    first_seg, first_idx, _ = words[i]
    last_seg, last_idx, _ = words[j]
    return Anchor(
        from_segment=first_seg.index,
        from_word=first_idx,
        to_segment=last_seg.index,
        to_word=last_idx,
        start_ms=first_seg.words[first_idx].start_ms,
        end_ms=last_seg.words[last_idx].end_ms,
    )


def whole_segment(seg: StoredSegment) -> Anchor:
    last = max(0, len(seg.words) - 1)
    return Anchor(seg.index, 0, seg.index, last, seg.start_ms, seg.end_ms)


def words_between(segments: list[StoredSegment], a: Anchor) -> str:
    out: list[str] = []
    for seg in segments:
        if seg.index < a.from_segment or seg.index > a.to_segment:
            continue
        start = a.from_word if seg.index == a.from_segment else 0
        end = a.to_word if seg.index == a.to_segment else len(seg.words) - 1
        out.extend(w.text for w in seg.words[start : end + 1])
    return " ".join(out)
