"""Mede a diarização num áudio com gabarito (`<áudio>.json`: [{start, end, speaker}]).

Transcreve com o STT padrão (os segmentos reais do app), atribui falantes ao vivo e
depois com o refinamento de fim de sessão, e conta os segmentos com o falante certo
(com o melhor mapeamento entre rótulos e o gabarito).

Uso: uv run --project backend python eval/diarization/run.py eval/diarization/out/debate.wav
"""

import argparse
import asyncio
import itertools
import json
import subprocess
from pathlib import Path

import numpy as np

from rtfc.diarization import MIN_EMBED_S, DiarizationService, OnlineClusterer, recluster
from rtfc.stt.files import transcribe_audio
from rtfc.stt.segmenter import Segment
from rtfc.stt.service import SttService

RATE = 16_000


def load(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar",
         str(RATE), "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def truth_for(seg: Segment, truth: list[dict]) -> str | None:
    best, best_o = None, 0.0
    for t in truth:
        o = min(seg.end, t["end"]) - max(seg.start, t["start"])
        if o > best_o:
            best, best_o = t["speaker"], o
    return best


def accuracy(pred: list, true: list) -> float:
    labels = sorted({p for p in pred if p is not None}, key=str)
    names = sorted({t for t in true if t is not None})
    best = 0
    for perm in itertools.permutations(labels, min(len(labels), len(names))):
        m = dict(zip(perm, names, strict=False))
        best = max(best, sum(m.get(p) == t for p, t in zip(pred, true, strict=True)))
    return best / len(true)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--threshold", type=float, nargs="+", default=[0.4, 0.5, 0.6])
    args = ap.parse_args()
    truth = json.loads(args.audio.with_suffix(".json").read_text())
    audio = load(args.audio)

    stt = SttService()
    segments: list[Segment] = []

    async def on_segment(seg: Segment, _lat: float) -> None:
        segments.append(seg)

    async def on_progress(_ms: int) -> None:
        pass

    await transcribe_audio(
        stt, audio, language="pt", on_segment=on_segment, on_progress=on_progress
    )
    true = [truth_for(s, truth) for s in segments]

    diar = DiarizationService()
    chunks = [audio[int(s.start * RATE) : int(s.end * RATE)] for s in segments]
    embs = await diar.embed_many(chunks)
    reliable = [s.end - s.start >= MIN_EMBED_S for s in segments]
    print(f"{args.audio.name}: {len(segments)} segmentos, {len(set(true))} falantes no gabarito")
    for thr in args.threshold:
        online = OnlineClusterer(thr)
        live: list[str | None] = []
        for e, r in zip(embs, reliable, strict=True):
            sid, merges = online.assign(e, reliable=r)
            live = [merges.get(x, x) if x else x for x in live]
            live.append(sid)
        refined = recluster(embs, reliable, thr)
        print(
            f"  limiar {thr}: ao vivo {accuracy(live, true):.0%} ({len(set(live))} falantes)"
            f" · refinado {accuracy(refined, true):.0%} ({len(set(refined))} falantes)"
        )


if __name__ == "__main__":
    asyncio.run(main())
