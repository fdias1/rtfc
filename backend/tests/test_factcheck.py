"""Integridade do veredicto, ranking das fontes, reserva da busca e fila de checagem."""

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from rtfc.config import MemorySecretStore, SearchSettings, SettingsStore
from rtfc.factcheck import service as service_mod
from rtfc.factcheck.pipeline import CheckOutcome
from rtfc.factcheck.service import PRIORITY_MANUAL, CheckContext, CheckService
from rtfc.factcheck.verdict import CitedSource, Evidence, VerdictResult, validate
from rtfc.search import service as search_service
from rtfc.search.base import SearchError, SearchResult
from rtfc.search.ranking import DomainLists, classify, rank
from rtfc.storage import CheckStore, ClaimStore, StoredClaim, TranscriptStore


def result(url: str, q: str = "q") -> SearchResult:
    return SearchResult(url=url, title=url, snippet="", provider="t", queries=(q,))


def evidence(n: int, url: str, text: str) -> Evidence:
    return Evidence(n, result(url).with_(tier="official"), text)


# --- Integridade (PRD RF5.4) ----------------------------------------------------

EVIDENCE = [
    evidence(1, "https://ibge.gov.br/a", "A taxa de desocupação foi de 5,3% no trimestre."),
    evidence(2, "https://g1.globo.com/b", "Desemprego cai para 5,3%, menor da série histórica."),
]


def test_invented_source_is_dropped_and_verdict_downgraded() -> None:
    raw = VerdictResult(
        verdict="falso",
        confidence=0.95,
        justification="Os dados mostram o contrário.",
        sources=[
            CitedSource(evidence=1, stance="refuta", quote="taxa de desocupação foi de 5,3%"),
            # Fonte que o modelo "inventou": não existe entre as evidências buscadas.
            CitedSource(evidence=99, stance="refuta", quote="www.site-inventado.com diz que"),
        ],
    )
    v = validate(raw, EVIDENCE, "pt")
    assert [s.result.url for s in v.sources] == ["https://ibge.gov.br/a"]
    assert v.dropped == 1
    assert v.verdict == "inconclusivo"
    assert v.confidence <= 0.3
    assert v.justification.startswith("Evidência insuficiente")


def test_valid_verdict_keeps_sources_and_cleans_quotes() -> None:
    raw = VerdictResult(
        verdict="falso",
        confidence=1.4,
        justification="Refutado.",
        sources=[
            CitedSource(evidence=1, stance="refuta", quote="“taxa de desocupação foi de 5,3%”"),
            CitedSource(evidence=1, stance="refuta", quote="repetida"),
            CitedSource(evidence=2, stance="refuta", quote="frase que não está no texto da página"),
        ],
    )
    v = validate(raw, EVIDENCE, "pt")
    assert v.verdict == "falso" and v.confidence == 1.0
    assert len(v.sources) == 2 and v.dropped == 1
    assert v.sources[0].quote == "taxa de desocupação foi de 5,3%"
    assert v.sources[1].quote == ""  # citação que não aparece na evidência é apagada


# --- Ranking ----------------------------------------------------------------------


def test_classify_tiers_and_blocklist() -> None:
    lists = DomainLists.for_language("pt", ("blogqualquer.com",))
    assert classify("https://www.aosfatos.org/x", lists) == "factchecker"
    assert classify("https://g1.globo.com/fato-ou-fake/x", lists) == "factchecker"
    assert classify("https://g1.globo.com/economia/x", lists) == "press"
    assert classify("https://www.ibge.gov.br/x", lists) == "primary"
    assert classify("https://www.scielo.br/j/artigo", lists) == "primary"
    assert classify("https://www.ufmg.br/estudo", lists) == "primary"
    assert classify("https://pt.wikipedia.org/wiki/X", lists) == "other"
    assert classify("https://exemplo.com/x", lists) == "other"
    assert classify("https://www.facebook.com/x", lists) is None
    assert classify("https://blogqualquer.com/x", lists) is None


def test_rank_orders_by_tier_merges_and_limits_per_domain() -> None:
    lists = DomainLists.for_language("pt")
    results = [
        result("https://exemplo.com/1", "q1"),
        result("https://g1.globo.com/a", "q1"),
        result("https://g1.globo.com/b", "q1"),
        result("https://g1.globo.com/c", "q1"),
        result("https://www.ibge.gov.br/x/", "q1"),
        result("https://ibge.gov.br/x", "q2"),  # mesma página por outra consulta
        result("https://lupa.uol.com.br/z", "q2"),
        result("https://tiktok.com/v", "q2"),
    ]
    ranked = rank(results, lists, limit=10)
    urls = [r.url for r in ranked]
    # Fonte primária primeiro, depois a agência de checagem, depois imprensa.
    assert urls[0] == "https://www.ibge.gov.br/x/"
    assert ranked[0].queries == ("q1", "q2")
    assert urls[1] == "https://lupa.uol.com.br/z"
    assert sum("g1.globo.com" in u for u in urls) == 2
    assert not any("tiktok" in u for u in urls)
    assert urls[-1] == "https://exemplo.com/1"


async def test_search_falls_back_to_duckduckgo(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        name = "searxng"

        async def search(self, query: str, *, language: str | None, limit: int) -> list[Any]:
            raise SearchError("SearXNG indisponível")

    class Ddg:
        name = "duckduckgo"

        async def search(self, query: str, *, language: str | None, limit: int) -> list[Any]:
            return [result(f"https://exemplo.com/{query}")]

    monkeypatch.setattr(search_service, "make_provider", lambda s, k: Down())
    monkeypatch.setattr(search_service, "DuckDuckGoProvider", Ddg)
    out = await search_service.search(
        ["a", "b"], language="pt", settings=SearchSettings(), secrets=MemorySecretStore()
    )
    assert out.provider == "duckduckgo"
    assert len(out.results) == 2 and out.warnings

    with pytest.raises(SearchError):
        await search_service.search(
            ["a"],
            language="pt",
            settings=SearchSettings(fallback_duckduckgo=False),
            secrets=MemorySecretStore(),
        )


# --- Fila -------------------------------------------------------------------------


def claim(i: str, *, dedup_of: str | None = None) -> StoredClaim:
    return StoredClaim(
        i, "s1", "auto", f"Afirmação {i}.", "", 0, 0, 0, 0, 0, 0, "queued", dedup_of, None,
        "2026-10-19T00:00:00", None,
    )  # fmt: skip


@pytest.fixture
async def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    db = TranscriptStore(tmp_path / "db").db
    claims, checks = ClaimStore(db), CheckStore(db)
    settings = SettingsStore(tmp_path / "settings.json", MemorySecretStore())
    settings.save(settings.settings.model_copy(update={"check_concurrency": 1}))
    events: list[Any] = []
    order: list[str] = []
    gates: dict[str, asyncio.Event] = {}

    async def fake_check(text: str, **kw: Any) -> CheckOutcome:
        cid = text.removeprefix("Afirmação ").rstrip(".")
        order.append(cid)
        await kw["on_stage"]("search")
        gate = gates.get(cid)
        if gate:
            await gate.wait()
        if cid == "boom":
            raise SearchError("busca fora do ar")
        from rtfc.factcheck.verdict import CheckedVerdict

        return CheckOutcome(
            CheckedVerdict("verdadeiro", 0.8, "ok", [], 0), [text], "fake", "m", 5, []
        )

    monkeypatch.setattr(service_mod, "check_claim", fake_check)

    async def broadcast(ev: Any) -> None:
        events.append(ev.claim)

    svc = CheckService(
        claims=claims,
        checks=checks,
        settings=settings,
        secrets=MemorySecretStore(),
        broadcast=broadcast,
        session_context=lambda sid, a, b: CheckContext("pt", date(2026, 10, 19)),
    )
    yield svc, claims, checks, events, order, gates
    await svc.stop()


async def wait_status(claims: ClaimStore, cid: str, status: str) -> None:
    for _ in range(200):
        c = claims.get(cid)
        if c and c.status == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{cid} não chegou a {status}: {claims.get(cid)}")


async def test_queue_runs_manual_first_and_stores_result(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, checks, events, order, gates = harness
    gates["a"] = asyncio.Event()
    for i in ("a", "b", "c"):
        claims.upsert(claim(i))
    await svc.enqueue(claims.get("a"))  # type: ignore[arg-type]
    await asyncio.sleep(0.02)  # "a" ocupa o único worker
    await svc.enqueue(claims.get("b"))  # type: ignore[arg-type]
    await svc.enqueue(claims.get("c"), priority=PRIORITY_MANUAL)  # type: ignore[arg-type]
    gates["a"].set()
    await wait_status(claims, "b", "done")
    assert order == ["a", "c", "b"]
    stored = checks.get("b")
    assert stored and stored.verdict == "verdadeiro"
    stages = [e.stage for e in events if e.id == "a" and e.status == "checking"]
    assert "search" in stages
    final = [e for e in events if e.id == "b"][-1]
    assert final.status == "done" and final.check.verdict == "verdadeiro"


async def test_cancel_running_and_queued(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, _, _, order, gates = harness
    gates["a"] = asyncio.Event()  # nunca liberado: só sai cancelando
    for i in ("a", "b"):
        claims.upsert(claim(i))
        await svc.enqueue(claims.get(i))  # type: ignore[arg-type]
    await asyncio.sleep(0.02)
    await svc.cancel("b")
    assert claims.get("b").status == "cancelled"  # type: ignore[union-attr]
    await svc.cancel("a")
    await wait_status(claims, "a", "cancelled")
    await asyncio.sleep(0.05)
    assert order == ["a"]  # "b" nunca rodou

    # Rechecar põe de volta na fila.
    await svc.retry("b")
    await wait_status(claims, "b", "done")


async def test_errors_and_duplicates_follow_original(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, _, events, _, _ = harness
    claims.upsert(claim("boom"))
    claims.upsert(claim("d"))
    claims.upsert(claim("d2", dedup_of="d"))
    await svc.enqueue(claims.get("boom"))  # type: ignore[arg-type]
    await wait_status(claims, "boom", "error")
    assert "busca fora do ar" in (claims.get("boom").error or "")  # type: ignore[union-attr]

    await svc.enqueue(claims.get("d"))  # type: ignore[arg-type]
    await wait_status(claims, "d2", "done")
    dup_event = [e for e in events if e.id == "d2"][-1]
    assert dup_event.check is not None  # a repetida mostra o resultado da original


async def test_discard_during_check_is_not_overwritten(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, _, _, _, gates = harness
    gates["x"] = asyncio.Event()
    claims.upsert(claim("x"))
    await svc.enqueue(claims.get("x"))  # type: ignore[arg-type]
    await wait_status(claims, "x", "checking")
    claims.upsert(claims.get("x").with_status("discarded"))  # type: ignore[union-attr]
    gates["x"].set()
    await asyncio.sleep(0.05)
    assert claims.get("x").status == "discarded"  # type: ignore[union-attr]


def test_press_cannot_take_every_slot() -> None:
    lists = DomainLists.for_language("pt")
    press = [result(f"https://{d}/n") for d in (
        "g1.globo.com", "folha.uol.com.br", "estadao.com.br", "cnnbrasil.com.br", "poder360.com.br",
    )]  # fmt: skip
    others = [result("https://www.ipea.gov.br/estudo"), result("https://blog.exemplo.com/post")]
    ranked = rank(press + others, lists, limit=10)
    tiers = [r.tier for r in ranked]
    assert tiers[0] == "primary"
    assert tiers.count("press") == 3  # cota da imprensa
    assert "other" in tiers  # outras fontes continuam entrando
