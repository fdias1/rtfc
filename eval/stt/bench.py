"""Benchmark de STT: latência por janela (modo ao vivo), RTF e WER em pt-BR.

Uso (da raiz do repo):
    eval/stt/make_reference.sh
    uv run --project backend --extra mlx python eval/stt/bench.py [--engines ...] [--models ...]

Métricas:
- `win_p50`/`win_p90`: segundos para transcrever uma janela de 10 s (o que o streaming faz
  a cada ~1 s). Precisa ficar bem abaixo de 1 s para a meta de ≤ 3 s fala → texto confirmado.
- `rtf`: tempo total / duração do áudio no modo arquivo (blocos de fala por VAD).
- `wer_clean`/`wer_noisy`: taxa de erro de palavras contra reference.txt.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import jiwer

from rtfc.stt import FasterWhisperEngine, MlxWhisperEngine
from rtfc.stt.base import STTEngine, pcm16_to_float32
from rtfc.stt.vad import chunk_by_speech

HERE = Path(__file__).resolve().parent
RATE = 16_000


def load_audio(path: Path):  # type: ignore[no-untyped-def]
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return pcm16_to_float32(pcm)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_engine(name: str, model: str) -> STTEngine:
    return MlxWhisperEngine(model) if name == "mlx-whisper" else FasterWhisperEngine(model)


def transcribe_file(engine: STTEngine, audio) -> tuple[str, float]:  # type: ignore[no-untyped-def]
    """Mesmo caminho do modo arquivo do app: blocos de fala por VAD, com o texto anterior como prompt."""
    t0 = time.perf_counter()
    parts: list[str] = []
    prompt = None
    for start, end in chunk_by_speech(audio):
        r = engine.transcribe(audio[start:end], language="pt", prompt=prompt)
        parts.append(r.text)
        prompt = " ".join(parts)[-200:] or None
    return " ".join(parts), time.perf_counter() - t0


def window_latencies(engine: STTEngine, audio, window_s: float = 10.0, n: int = 8) -> list[float]:  # type: ignore[no-untyped-def]
    win = int(window_s * RATE)
    starts = [int(i * (len(audio) - win) / max(1, n - 1)) for i in range(n)]
    out = []
    for s in starts:
        t0 = time.perf_counter()
        engine.transcribe(audio[s : s + win], language="pt")
        out.append(time.perf_counter() - t0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", default=["faster-whisper", "mlx-whisper"])
    ap.add_argument("--models", nargs="+", default=["small", "medium", "large-v3-turbo"])
    args = ap.parse_args()

    ref = normalize((HERE / "reference.txt").read_text(encoding="utf-8"))
    clean = load_audio(HERE / "out/ref_clean.wav")
    noisy = load_audio(HERE / "out/ref_noisy.wav")
    duration = len(clean) / RATE
    results = []

    for engine_name in args.engines:
        for model in args.models:
            print(f"== {engine_name} / {model}", file=sys.stderr, flush=True)
            engine = make_engine(engine_name, model)
            t0 = time.perf_counter()
            engine.load()
            load_s = time.perf_counter() - t0
            engine.transcribe(clean[: 3 * RATE], language="pt")  # aquecimento

            lat = window_latencies(engine, clean)
            hyp_clean, t_clean = transcribe_file(engine, clean)
            hyp_noisy, _ = transcribe_file(engine, noisy)
            (HERE / "out").mkdir(exist_ok=True)
            (HERE / f"out/hyp_{engine_name}_{model}.txt").write_text(hyp_clean, encoding="utf-8")
            row = {
                "engine": engine_name,
                "model": model,
                "load_s": round(load_s, 1),
                "win_p50": round(statistics.median(lat), 2),
                "win_p90": round(sorted(lat)[int(0.9 * (len(lat) - 1))], 2),
                "rtf": round(t_clean / duration, 3),
                "wer_clean": round(jiwer.wer(ref, normalize(hyp_clean)), 3),
                "wer_noisy": round(jiwer.wer(ref, normalize(hyp_noisy)), 3),
            }
            print(json.dumps(row), file=sys.stderr, flush=True)
            results.append(row)
            del engine

    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/results.json").write_text(json.dumps(results, indent=2))
    cols = ["engine", "model", "load_s", "win_p50", "win_p90", "rtf", "wer_clean", "wer_noisy"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in results:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
