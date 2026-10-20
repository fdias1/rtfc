"""Checagem de uma afirmação: consultas → busca → leitura → veredicto → integridade."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from rtfc.config import SearchSettings, SecretStore
from rtfc.factcheck.verdict import (
    EVIDENCE_CHARS,
    CheckedVerdict,
    ClaimBackground,
    Evidence,
    judge,
    plan_queries,
    relevant_passage,
    validate,
)
from rtfc.llm import LlmClient
from rtfc.search.base import SearchResult
from rtfc.search.fetch import fetch_text
from rtfc.search.ranking import DomainLists, rank
from rtfc.search.service import search

log = logging.getLogger(__name__)

Stage = Literal["queries", "search", "reading", "analysis"]
StageCallback = Callable[[Stage], Awaitable[None]]

MAX_QUERIES = 3
"""Menos consultas por afirmação = menos bloqueio pelos buscadores (a 1ª é a da fonte primária)."""
CANDIDATES = 10
"""Resultados ranqueados que tentamos ler."""
MAX_EVIDENCE = 6
FETCH_CONCURRENCY = 6


@dataclass(frozen=True)
class CheckOutcome:
    verdict: CheckedVerdict
    queries: list[str]
    search_provider: str
    model: str
    duration_ms: int
    warnings: list[str]


LOCAL_MAX_EVIDENCE = 5
LOCAL_EVIDENCE_CHARS = 1100
"""Modelo local processa ~180 tokens/s de entrada neste hardware: evidência mais enxuta."""


async def _read(
    results: list[SearchResult],
    claim: str,
    *,
    max_evidence: int = MAX_EVIDENCE,
    chars: int = EVIDENCE_CHARS,
) -> list[Evidence]:
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(r: SearchResult) -> tuple[SearchResult, str | None]:
        if r.content:
            return r, r.content
        async with sem:
            return r, await fetch_text(r.url)

    pages = await asyncio.gather(*(one(r) for r in results))
    evidence: list[Evidence] = []
    # Páginas lidas primeiro; sem texto, o snippet do buscador vale como evidência fraca.
    with_text = [(r, t) for r, t in pages if t]
    snippets = [(r, None) for r, t in pages if not t and len(r.snippet) > 60]
    chosen = (with_text + snippets)[:max_evidence]
    # Comparar parágrafos de páginas grandes (PDFs de dezenas de páginas) é CPU pesada:
    # fora do event loop, para não travar o WebSocket.
    bodies = await asyncio.gather(
        *(
            asyncio.to_thread(relevant_passage, text, claim, chars) if text else _value(r.snippet)
            for r, text in chosen
        )
    )
    for (r, _), body in zip(chosen, bodies, strict=True):
        evidence.append(Evidence(len(evidence) + 1, r.with_(content=None), body))
    return evidence


async def _value(text: str) -> str:
    return text


async def check_claim(
    claim: str,
    *,
    client: LlmClient,
    search_settings: SearchSettings,
    secrets: SecretStore,
    language: str | None,
    when: date,
    on_stage: StageCallback,
    claim_context: str | None = None,
    content_context: str | None = None,
    speaker: str | None = None,
    transcript: str = "",
    full_evidence: bool = False,
) -> CheckOutcome:
    t0 = time.perf_counter()
    background = ClaimBackground(
        claim_context=claim_context,
        content_context=content_context,
        speaker=speaker,
        transcript=transcript,
    )

    await on_stage("queries")
    plan = await plan_queries(client, claim, language=language, when=when, background=background)
    queries = [q.strip() for q in plan.value.queries if q.strip()][:MAX_QUERIES] or [claim]

    await on_stage("search")
    found = await search(queries, language=language, settings=search_settings, secrets=secrets)
    lists = DomainLists.for_language(language, tuple(search_settings.blocked_domains))
    candidates = rank(found.results, lists, CANDIDATES)

    await on_stage("reading")
    if client.is_local and not full_evidence:
        evidence = await _read(
            candidates, claim, max_evidence=LOCAL_MAX_EVIDENCE, chars=LOCAL_EVIDENCE_CHARS
        )
    else:
        evidence = await _read(candidates, claim)

    await on_stage("analysis")
    if evidence:
        raw = await judge(
            client, claim, evidence, language=language, when=when, background=background
        )
        verdict = validate(raw.value, evidence, language)
        model = raw.model
    else:
        verdict = CheckedVerdict(
            "inconclusivo", 0.0, "Nenhuma fonte foi encontrada para esta afirmação.", [], 0
        )
        model = client.litellm_model
    duration = round((time.perf_counter() - t0) * 1000)
    log.info(
        "checagem em %.1fs: %s (%d fontes, %d citações descartadas, busca=%s)",
        duration / 1000, verdict.verdict, len(verdict.sources), verdict.dropped, found.provider,
    )  # fmt: skip
    return CheckOutcome(verdict, queries, found.provider, model, duration, found.warnings)
