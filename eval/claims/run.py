"""Avaliação da extração de afirmações (recall, falsos positivos, latência por chamada).

Usa o texto de referência como transcrição (uma frase por segmento, sem STT) e passa as
frases pelo ClaimPipeline real, uma a uma, como chegariam ao vivo.

Uso (da raiz):  uv run --project backend python eval/claims/run.py ollama:qwen3:8b openai:gpt-5.4-mini
"""

import asyncio
import json
import re
import statistics
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from rtfc.claims import ClaimPipeline
from rtfc.config import KeyringSecretStore, LlmRole
from rtfc.llm import LlmClient
from rtfc.storage import ClaimStore, StoredSegment, StoredWord, TranscriptStore

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "stt" / "reference.txt"
CONTEXT = "Discurso político de campanha no Brasil, 2026; o orador fala de educação, saúde, economia e meio ambiente."


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def segments() -> list[StoredSegment]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", REF.read_text(encoding="utf-8")) if s.strip()]
    out, t = [], 0
    for i, sent in enumerate(sentences):
        words = []
        for w in sent.split():
            words.append(StoredWord(t, t + 300, w, 1.0))
            t += 320
        out.append(StoredSegment(i, words[0].start_ms, words[-1].end_ms, sent, tuple(words)))
        t += 600
    return out


def matches(claim: str, keywords: list[str]) -> bool:
    c = norm(claim)
    return all(k in c for k in keywords)


async def evaluate(spec: str) -> dict:
    provider, model = spec.split(":", 1)
    role = LlmRole(provider=provider, model=model)
    secrets = KeyringSecretStore()
    tmp = Path(tempfile.mkdtemp())
    store = ClaimStore(TranscriptStore(tmp / "db").db)
    calls: list[float] = []
    errors: list[str] = []

    async def emit(ev):  # type: ignore[no-untyped-def]
        if ev.type == "extractor.status" and ev.state == "error":
            errors.append(ev.message)

    pipe = ClaimPipeline(
        "eval",
        client_factory=lambda: LlmClient(role, secrets),
        store=store,
        emit=emit,
        language=lambda: "pt",
        content_context=lambda: CONTEXT,
        min_score=lambda: 4,
    )
    pipe.start()
    # Aquecimento (carrega o modelo local) fora da medição.
    await LlmClient(role, secrets).structured([{"role": "user", "content": 'Responda {"claims": [], "last_sentence_incomplete": false}'}], __import__("rtfc.claims.extractor", fromlist=["ExtractionResult"]).ExtractionResult)
    for seg in segments():
        t0 = time.perf_counter()
        pipe.submit(seg)
        while pipe._pending or pipe._state[0] == "running":  # noqa: SLF001 — avaliação mede o pipeline real
            await asyncio.sleep(0.02)
        calls.append(time.perf_counter() - t0)
    await pipe.close()

    gold = json.loads((HERE / "reference_claims.json").read_text(encoding="utf-8"))
    claims = [c.text for c in store.for_session("eval") if c.dedup_of is None]
    found = [e["id"] for e in gold["expected"] if any(matches(c, e["keywords"]) for c in claims)]
    false_pos = [c for c in claims if any(matches(c, n["keywords"]) for n in gold["negatives"])]
    optional = [c for c in claims if any(matches(c, o["keywords"]) for o in gold.get("optional", []))]
    return {
        "model": spec,
        "claims": len(claims),
        "recall": round(len(found) / len(gold["expected"]), 2),
        "missed": [e["id"] for e in gold["expected"] if e["id"] not in found],
        "false_positive_rate": round(len(false_pos) / max(1, len(claims)), 2),
        "false_positives": false_pos,
        "optional_extracted": len(optional),
        "call_p50_s": round(statistics.median(calls), 2),
        "call_p90_s": round(sorted(calls)[int(0.9 * (len(calls) - 1))], 2),
        "errors": errors[:3],
        "extracted": claims,
    }


async def main() -> None:
    for spec in sys.argv[1:] or ["ollama:qwen3:8b"]:
        print(json.dumps(await evaluate(spec), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
