"""Avaliação dos veredictos contra checagens publicadas (eval/verdicts/dataset.jsonl).

Roda o pipeline real de checagem (consultas → busca → leitura → veredicto) para cada
afirmação e compara com o selo da agência, já mapeado para os 4 veredictos do rtfc.

Por padrão os domínios das agências de checagem ficam BLOQUEADOS na busca: senão o rtfc
acharia a própria checagem e "colaria" a resposta. `--allow-factcheckers` mede com elas.

Uso (da raiz):
    uv run --project backend python eval/verdicts/run.py [--model openai:gpt-5.4-mini] [--limit N]
Saída: eval/verdicts/out/<rótulo>.jsonl e .md
"""

import argparse
import asyncio
import collections
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from rtfc.config import KeyringSecretStore, LlmRole, SearchSettings
from rtfc.factcheck.pipeline import check_claim
from rtfc.llm import LlmClient, LlmError
from rtfc.search.base import SearchError
from rtfc.search.data import TIERS

HERE = Path(__file__).resolve().parent
LABELS = ["verdadeiro", "fora_de_contexto", "falso", "inconclusivo"]
# Leitura "de direção": a afirmação se sustenta ou é problemática?
DIRECTION = {
    "verdadeiro": "ok",
    "fora_de_contexto": "problema",
    "falso": "problema",
    "inconclusivo": "?",
}


async def check_one(row: dict, client: LlmClient, search: SearchSettings, secrets) -> dict:  # type: ignore[no-untyped-def,type-arg]
    t0 = time.perf_counter()
    try:
        when = date.fromisoformat(row["said_on"][:10])
    except ValueError:
        when = date.today()

    async def stage(_: str) -> None:
        pass

    try:
        out = await check_claim(
            row["claim"],
            client=client,
            search_settings=search,
            secrets=secrets,
            language="pt",
            when=when,
            on_stage=stage,
            claim_context=f"Dito por {row['speaker']} em {when.isoformat()}, no Brasil.",
            speaker=row["speaker"],
        )
    except (LlmError, SearchError) as exc:
        return {**row, "got": "erro", "error": str(exc)[:200], "seconds": time.perf_counter() - t0}
    v = out.verdict
    return {
        **row,
        "got": v.verdict,
        "confidence": round(v.confidence, 2),
        "justification": v.justification,
        "sources": [{"url": s.result.url, "tier": s.result.tier, "stance": s.stance} for s in v.sources],
        "dropped_citations": v.dropped,
        "search_provider": out.search_provider,
        "seconds": round(out.duration_ms / 1000, 1),
    }


def report(rows: list[dict], label: str, blocked: bool) -> str:  # type: ignore[type-arg]
    done = [r for r in rows if r["got"] != "erro"]
    n = len(done)
    exact = sum(r["got"] == r["expected"] for r in done)
    direction = sum(DIRECTION[r["got"]] == DIRECTION[r["expected"]] for r in done)
    decided = [r for r in done if r["got"] != "inconclusivo"]
    decided_ok = sum(r["got"] == r["expected"] for r in decided)
    conf: dict[str, collections.Counter[str]] = {e: collections.Counter() for e in LABELS}
    for r in done:
        conf[r["expected"]][r["got"]] += 1
    tiers = collections.Counter(s["tier"] for r in done for s in r["sources"])
    secs = sorted(r["seconds"] for r in done) or [0.0]

    lines = [
        f"# Avaliação de veredictos — {label}",
        "",
        f"- Afirmações: {len(rows)} ({len(rows) - n} com erro de busca/LLM)",
        f"- Agências de checagem na busca: {'**bloqueadas**' if blocked else 'permitidas'}",
        f"- **Concordância exata (4 classes): {exact}/{n} = {exact / max(1, n):.0%}**",
        f"- Concordância de direção (se sustenta × problemática × inconclusivo): {direction / max(1, n):.0%}",
        f"- Inconclusivos do rtfc: {n - len(decided)} ({(n - len(decided)) / max(1, n):.0%})",
        f"- Acerto quando o rtfc decide (sem inconclusivos): {decided_ok}/{len(decided)} = {decided_ok / max(1, len(decided)):.0%}",
        f"- Citações inválidas descartadas pela validação: {sum(r['dropped_citations'] for r in done)}",
        f"- Tempo por checagem: p50 {statistics.median(secs):.1f} s · p90 {secs[int(0.9 * (len(secs) - 1))]:.1f} s",
        f"- Fontes citadas por tipo: {dict(tiers)}",
        "",
        "## Matriz de confusão (linhas = agência, colunas = rtfc)",
        "",
        "| agência \\ rtfc | " + " | ".join(LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
    ]
    for e in LABELS:
        lines.append(f"| {e} | " + " | ".join(str(conf[e][g]) for g in LABELS) + " |")
    misses = [r for r in done if DIRECTION[r["got"]] not in ("?", DIRECTION[r["expected"]])]
    if misses:
        lines += ["", "## Erros de direção (o rtfc disse o oposto da agência)", ""]
        for r in misses[:25]:
            lines.append(
                f"- **{r['expected']} → {r['got']}** · {r['speaker']}: “{r['claim']}” "
                f"([checagem]({r['source_url']}))  \n  rtfc: {r['justification']}"
            )
    return "\n".join(lines) + "\n"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ollama:qwen3:8b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--sample", type=int, default=0, help="amostra estratificada por veredicto esperado"
    )
    ap.add_argument("--concurrency", type=int, default=0, help="padrão: 1 local, 2 online")
    ap.add_argument("--allow-factcheckers", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(line) for line in (HERE / "dataset.jsonl").open(encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    if args.sample:
        # Proporcional por classe, com pelo menos 2 de cada; ordem fixa (reprodutível).
        by: dict[str, list[dict]] = collections.defaultdict(list)  # type: ignore[type-arg]
        for r in rows:
            by[r["expected"]].append(r)
        picked: list[dict] = []  # type: ignore[type-arg]
        for label, items in by.items():
            k = max(2, round(args.sample * len(items) / len(rows)))
            step = max(1, len(items) // k)
            picked += items[::step][:k]
        rows = picked
    blocked = not args.allow_factcheckers
    search = SearchSettings(blocked_domains=list(TIERS["pt"]["factchecker"]) if blocked else [])
    provider, model = args.model.split(":", 1)
    secrets = KeyringSecretStore()
    client = LlmClient(LlmRole(provider=provider, model=model), secrets)

    concurrency = args.concurrency or (1 if provider == "ollama" else 2)
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []  # type: ignore[type-arg]

    async def run(row: dict) -> None:  # type: ignore[type-arg]
        async with sem:
            res = await check_one(row, client, search, secrets)
            results.append(res)
            print(f"[{len(results)}/{len(rows)}] {res['expected']:>16} → {res['got']:<16} {res['claim'][:70]}", file=sys.stderr)

    await asyncio.gather(*(run(r) for r in rows))
    label = f"{model.replace(':', '-')}{'' if blocked else '-com-checadores'}" + (
        f"-amostra{len(rows)}" if args.sample else ""
    )
    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / f"{label}.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    md = report(results, label, blocked)
    (out_dir / f"{label}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
