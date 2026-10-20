"""Exportação da sessão (M7): relatório Markdown, JSON completo, SRT e VTT."""

import json
from pathlib import Path

import pytest

from rtfc.config import MemorySecretStore, SettingsStore
from rtfc.sessions import Session, SessionError, SessionManager
from rtfc.storage import StoredCheck, StoredClaim, StoredSegment, StoredSource, TranscriptStore


def claim(cid: str, seg: int, status: str, **kw: object) -> StoredClaim:
    base = dict(
        id=cid, session_id="", origin="auto", text=f"Afirmação {cid} normalizada.",
        source_text=f"afirmação {cid} como dita", from_segment=seg, from_word=0,
        to_segment=seg, to_word=1, start_ms=seg * 2000, end_ms=seg * 2000 + 1500,
        status=status, dedup_of=None, speaker="S1" if seg == 0 else "S2",
        created_at="2026-10-19T00:00:00", model="m",
    )  # fmt: skip
    base.update(kw)
    return StoredClaim(**base)  # type: ignore[arg-type]


def check(cid: str, verdict: str, model: str) -> StoredCheck:
    src = StoredSource(
        "https://ibge.gov.br/x",
        "PNAD Contínua",
        "ibge.gov.br",
        "primary",
        "refuta",
        "taxa de 6%",
        None,
    )
    return StoredCheck(cid, verdict, 0.8, f"Justificativa {verdict}.", model, "searxng", ("q",),
                       "2026-10-19T00:00:00", 1000, (src,))  # fmt: skip


@pytest.fixture
def setup(tmp_path: Path) -> tuple[SessionManager, str]:
    store = TranscriptStore(tmp_path / "db.sqlite")
    secrets = MemorySecretStore()
    m = SessionManager(
        tmp_path / "sessions",
        store=store,
        settings=SettingsStore(tmp_path / "s.json", secrets),
        secrets=secrets,
    )
    info = m._new_info("system", "pt", "Debate na TV", status="completed", duration_ms=6000)
    info.title = "Debate / final"
    info.speakers = {"S1": "Ana"}
    Session.write_info(info)
    sid = info.id
    store.add_segment(sid, StoredSegment(0, 0, 1500, "O desemprego é de 4%.", (), "S1"))
    store.add_segment(sid, StoredSegment(1, 2000, 3500, "Não é verdade.", (), "S2"))
    store.add_segment(sid, StoredSegment(2, 4000, 5500, "É sim.", (), "S2"))
    assert m.claim_store
    m.claim_store.upsert(claim("a", 0, "done", session_id=sid, review_status="done"))
    m.claim_store.upsert(claim("b", 1, "error", session_id=sid, error="Ollama fora"))
    m.claim_store.upsert(claim("c", 2, "discarded", session_id=sid))
    m.check_store.save(check("a", "verdadeiro", "qwen3:8b"), "live")
    m.check_store.save(check("a", "falso", "qwen3:14b"), "review")
    return m, sid


def test_markdown_report(setup: tuple[SessionManager, str]) -> None:
    m, sid = setup
    name, md = m.export(sid, "md")
    assert name.endswith("Debate _ final.md") and name.startswith("rtfc ")
    assert md.startswith("# Debate / final\n")
    assert "## Contexto\n\nDebate na TV" in md
    assert "- Ana\n- Falante 2" in md
    assert "2 afirmações; 1 checadas." in md and "- Falso: 1" in md
    assert "### [00:00] Ana" in md
    assert "**Veredicto: Falso** · confiança 80% · revisado com qwen3:14b" in md
    assert "(na checagem ao vivo: Verdadeiro)" in md
    assert "[PNAD Contínua](https://ibge.gov.br/x) · ibge.gov.br · fonte primária · refuta" in md
    assert "**Veredicto:** — (erro na checagem)" in md
    assert "afirmação c" not in md  # descartada
    assert "**[00:02] Falante 2:** Não é verdade." in md
    assert "[00:04] É sim." in md  # mesmo falante: sem repetir o nome


def test_json_has_everything(setup: tuple[SessionManager, str]) -> None:
    m, sid = setup
    data = json.loads(m.export(sid, "json")[1])
    assert data["format"] == "rtfc-session" and data["session"]["id"] == sid
    assert data["speakers"] == {"S1": "Ana", "S2": "Falante 2"}
    assert len(data["segments"]) == 3
    a = next(c for c in data["claims"] if c["id"] == "a")
    assert a["checks"]["live"]["verdict"] == "verdadeiro"
    assert a["checks"]["review"]["verdict"] == "falso"


def test_subtitles(setup: tuple[SessionManager, str]) -> None:
    m, sid = setup
    srt = m.export(sid, "srt")[1]
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nAna: O desemprego é de 4%.\n")
    vtt = m.export(sid, "vtt")[1]
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\n<v Ana>O desemprego")
    assert vtt.count("-->") == 3


def test_active_session_cannot_be_exported(setup: tuple[SessionManager, str]) -> None:
    m, sid = setup
    m._sessions[sid] = object()  # type: ignore[assignment]
    with pytest.raises(SessionError):
        m.export(sid, "md")
