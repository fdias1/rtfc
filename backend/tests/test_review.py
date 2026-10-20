"""Rechecagem com o modelo de qualidade (M6.1): fila, pausa, cancelamento, memória, histórico."""

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from rtfc.config import LlmRole, MemorySecretStore, SettingsStore
from rtfc.factcheck import review as review_mod
from rtfc.factcheck.pipeline import CheckOutcome
from rtfc.factcheck.review import ReviewService
from rtfc.factcheck.service import CheckContext, CheckService
from rtfc.factcheck.verdict import CheckedVerdict
from rtfc.storage import CheckStore, ClaimStore, StoredCheck, StoredClaim, TranscriptStore


def claim(i: str, **kw: Any) -> StoredClaim:
    base = dict(
        id=i, session_id="s1", origin="auto", text=f"Afirmação {i}.", source_text="",
        from_segment=0, from_word=0, to_segment=0, to_word=0, start_ms=0, end_ms=0,
        status="done", dedup_of=None, speaker=None, created_at="2026-10-19T00:00:00",
        model=None,
    )  # fmt: skip
    base.update(kw)
    return StoredClaim(**base)  # type: ignore[arg-type]


def live_check(cid: str, verdict: str) -> StoredCheck:
    return StoredCheck(cid, verdict, 0.5, "rápido", "fast", "fake", (), "t", 1, ())


class FakeStt:
    def __init__(self) -> None:
        self.unloads = 0

    async def unload(self) -> bool:
        self.unloads += 1
        return True


@pytest.fixture
async def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    db = TranscriptStore(tmp_path / "db").db
    claims, checks = ClaimStore(db), CheckStore(db)
    settings = SettingsStore(tmp_path / "settings.json", MemorySecretStore())
    settings.save(
        settings.settings.model_copy(
            update={
                "checker": LlmRole(provider="ollama", model="qwen3:8b"),
                "extractor": LlmRole(provider="ollama", model="qwen3:8b"),
                "reviewer": LlmRole(provider="ollama", model="qwen3:14b"),
            }
        )
    )
    events: list[Any] = []
    unloaded: list[str] = []
    gates: dict[str, asyncio.Event] = {}
    calls: list[tuple[str, bool]] = []

    async def fake_check(text: str, **kw: Any) -> CheckOutcome:
        cid = text.removeprefix("Afirmação ").rstrip(".")
        calls.append((cid, kw["full_evidence"]))
        await kw["on_stage"]("analysis")
        if cid in gates:
            await gates[cid].wait()
        return CheckOutcome(CheckedVerdict("falso", 0.9, "revisado", [], 0), [], "fake", "m", 5, [])

    async def fake_unload(model: str, base_url: str | None = None) -> bool:
        unloaded.append(model)
        return True

    monkeypatch.setattr(review_mod, "check_claim", fake_check)
    monkeypatch.setattr(review_mod, "ollama_unload", fake_unload)

    async def broadcast(ev: Any) -> None:
        events.append(ev)

    ctx = lambda sid, a, b: CheckContext("pt", date(2026, 10, 19))  # noqa: E731
    checker = CheckService(
        claims=claims, checks=checks, settings=settings, secrets=MemorySecretStore(),
        broadcast=broadcast, session_context=ctx,
    )  # fmt: skip
    stt = FakeStt()
    svc = ReviewService(
        claims=claims, checks=checks, check_service=checker, settings=settings,
        secrets=MemorySecretStore(), broadcast=broadcast, session_context=ctx, stt=stt,  # type: ignore[arg-type]
    )  # fmt: skip
    yield svc, claims, checks, events, unloaded, gates, calls, stt
    await svc.stop()


async def wait_review(svc: ReviewService, sid: str = "s1") -> None:
    for _ in range(300):
        if svc.status(sid).state in ("done", "cancelled"):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(svc.status(sid))


async def test_review_rechecks_frees_memory_and_keeps_history(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, checks, events, unloaded, _, calls, stt = harness
    claims.upsert(claim("a"))
    checks.save(live_check("a", "verdadeiro"))
    claims.upsert(claim("b"))
    claims.upsert(claim("d", dedup_of="a"))
    claims.upsert(claim("x", status="discarded"))

    status = await svc.start("s1", "all")
    assert status.total == 2  # sem repetidas e descartadas
    await wait_review(svc)
    assert svc.status("s1").done == 2
    # Antes: Whisper e modelo rápido fora da memória. Depois: revisor descarregado.
    assert stt.unloads == 1
    assert unloaded == ["qwen3:8b", "qwen3:14b"]
    assert all(full for _, full in calls)  # orçamento de evidência completo
    # Histórico: a checagem ao vivo continua lá; a revisão vira o resultado principal.
    assert checks.get("a", "live").verdict == "verdadeiro"  # type: ignore[union-attr]
    assert checks.get("a", "review").verdict == "falso"  # type: ignore[union-attr]
    data = svc._check_service.data(claims.get("a"))  # type: ignore[arg-type]
    assert data.reviewed and data.check.verdict == "falso"  # type: ignore[attr-defined]
    assert data.previous_verdict == "verdadeiro"  # type: ignore[attr-defined]
    assert claims.get("a").review_status == "done"  # type: ignore[union-attr]
    # A repetida também mostra o resultado revisado.
    assert svc._check_service.data(claims.get("d")).check.verdict == "falso"  # type: ignore[arg-type,attr-defined]
    states = [e.state for e in events if e.type == "review.status"]
    assert "preparing" in states and states[-1] == "done"

    # "pending": nada mais a revisar.
    assert (await svc.start("s1", "pending")).total == 0


async def test_doubtful_scope_selects_only_weak_results(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, checks, *_ = harness
    for cid, verdict in (("v", "verdadeiro"), ("i", "inconclusivo"), ("f", "fora_de_contexto")):
        claims.upsert(claim(cid))
        checks.save(live_check(cid, verdict))
    claims.upsert(claim("e", status="error"))
    assert sorted(c.id for c in svc.select("s1", "doubtful")) == ["e", "f", "i"]


async def test_pause_redoes_current_claim_and_cancel_stops(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, checks, _, unloaded, gates, calls, _ = harness
    gates["a"] = asyncio.Event()
    gates["c"] = asyncio.Event()  # segura a "c" para cancelar no meio
    for cid in ("a", "b", "c"):
        claims.upsert(claim(cid))
    await svc.start("s1", "all")
    await asyncio.sleep(0.05)
    assert claims.get("a").review_status == "checking"  # type: ignore[union-attr]

    await svc.pause()  # sessão ao vivo começou
    await asyncio.sleep(0.05)
    assert svc.status("s1").state == "paused"
    assert claims.get("a").review_status == "queued"  # type: ignore[union-attr]
    assert "qwen3:14b" in unloaded  # memória devolvida

    gates["a"].set()
    await svc.resume()
    for _ in range(100):
        if claims.get("a").review_status == "done":  # type: ignore[union-attr]
            break
        await asyncio.sleep(0.01)
    assert [c for c, _ in calls].count("a") == 2  # refeita depois da pausa

    for _ in range(100):
        if claims.get("c").review_status == "checking":  # type: ignore[union-attr]
            break
        await asyncio.sleep(0.01)
    await svc.cancel("s1")
    await wait_review(svc)
    assert svc.status("s1").state == "cancelled"
    assert claims.get("c").review_status == "cancelled"  # type: ignore[union-attr]
    assert checks.get("c", "review") is None


async def test_waits_for_live_check_before_reviewing(harness) -> None:  # type: ignore[no-untyped-def]
    svc, claims, _, _, _, _, calls, _ = harness
    review_mod.WAIT_LIVE_CHECK_S = 0.01  # type: ignore[misc]
    claims.upsert(claim("a", status="checking"))
    await svc.start("s1", "all")
    await asyncio.sleep(0.1)
    assert calls == []
    claims.upsert(claims.get("a").with_status("done"))  # type: ignore[union-attr]
    await wait_review(svc)
    assert [c for c, _ in calls] == ["a"]


def test_check_store_migrates_v1_table(tmp_path: Path) -> None:
    db = TranscriptStore(tmp_path / "db").db
    db.executescript(
        "CREATE TABLE check_result (claim_id TEXT PRIMARY KEY, verdict TEXT, confidence REAL,"
        " justification TEXT, model TEXT, search_provider TEXT, queries TEXT, checked_at TEXT,"
        " duration_ms INTEGER, sources TEXT);"
        "INSERT INTO check_result VALUES ('a','falso',0.8,'j','m','p','[]','t',3,'[]');"
    )
    store = CheckStore(db)
    assert store.get("a", "live").verdict == "falso"  # type: ignore[union-attr]
    assert store.get("a", "review") is None
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='check_result'").fetchone()
