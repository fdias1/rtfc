"""Extração de afirmações com um LLM falso: ancoragem, deduplicação, agrupamento e frase cortada."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from rtfc.claims import ClaimPipeline, anchor, find_duplicate
from rtfc.claims.extractor import ExtractedClaim, ExtractionResult, NormalizedClaim
from rtfc.llm import LlmError, LlmResult
from rtfc.storage import ClaimStore, StoredSegment, StoredWord, TranscriptStore


def seg(index: int, text: str, start_ms: int = 0) -> StoredSegment:
    words, t = [], start_ms
    for w in text.split():
        words.append(StoredWord(t, t + 300, w, 1.0))
        t += 350
    return StoredSegment(index, words[0].start_ms, words[-1].end_ms, text, tuple(words))


class FakeClient:
    """Devolve respostas programadas e guarda as mensagens recebidas."""

    def __init__(self, replies: list[BaseModel | Exception], delay: float = 0.0) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []
        self.delay = delay

    async def structured(self, messages: list[dict[str, str]], schema: type[Any]) -> LlmResult[Any]:
        self.calls.append(messages)
        await asyncio.sleep(self.delay)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LlmResult(reply, 10, "fake/model")


@pytest.fixture
def store(tmp_path: Path) -> ClaimStore:
    return ClaimStore(TranscriptStore(tmp_path / "db").db)


def make_pipeline(store: ClaimStore, client: FakeClient, events: list[Any]) -> ClaimPipeline:
    async def emit(ev: Any) -> None:
        events.append(ev)

    return ClaimPipeline(
        "s1", client_factory=lambda: client, store=store, emit=emit, language=lambda: "pt"
    )


def test_anchor_finds_words_even_with_small_differences() -> None:
    s = seg(3, "Segundo o ministério, mais da metade dos alunos não termina os estudos.")
    a = anchor("mais da metade dos alunos nao termina", [s])
    assert a is not None
    assert (a.from_segment, a.from_word, a.to_segment, a.to_word) == (3, 3, 3, 9)
    assert a.start_ms == s.words[3].start_ms
    assert anchor("frase que não existe de jeito nenhum aqui", [s]) is None


def test_anchor_can_cross_segments() -> None:
    a = anchor(
        "caiu muito e o desemprego",
        [seg(0, "A inflação caiu muito"), seg(1, "e o desemprego subiu.")],
    )
    assert a is not None and (a.from_segment, a.to_segment) == (0, 1)


def test_dedup_matches_rephrasings() -> None:
    from rtfc.storage import StoredClaim

    existing = StoredClaim(
        "a", "s1", "auto", "A inflação caiu no último trimestre.", "", 0, 0, 0, 0, 0, 0,
        "queued", None, None, "t", None,
    )  # fmt: skip
    assert find_duplicate("a inflacao caiu no ultimo trimestre", [existing]) is existing
    assert find_duplicate("O desemprego subiu no último trimestre.", [existing]) is None


async def test_pipeline_extracts_anchors_and_dedups(store: ClaimStore) -> None:
    client = FakeClient(
        [
            ExtractionResult(
                claims=[
                    ExtractedClaim(
                        segment_index=0, source_text="a inflação caiu", claim="A inflação caiu."
                    )
                ],
                last_sentence_incomplete=False,
            ),
            ExtractionResult(
                claims=[
                    ExtractedClaim(
                        segment_index=1, source_text="a inflação caiu", claim="A inflação caiu."
                    )
                ],
                last_sentence_incomplete=False,
            ),
        ]
    )
    events: list[Any] = []
    pipe = make_pipeline(store, client, events)
    pipe.start()
    pipe.submit(seg(0, "Eu digo que a inflação caiu."))
    await asyncio.sleep(0.05)
    pipe.submit(seg(1, "Repito: a inflação caiu.", 5000))
    await pipe.close()

    claims = store.for_session("s1")
    assert len(claims) == 2
    first, second = claims
    assert (first.from_segment, first.from_word, first.to_word) == (0, 3, 5)
    assert first.status == "queued" and first.dedup_of is None
    assert second.dedup_of == first.id
    updates = [e for e in events if e.type == "claim.updated"]
    assert [u.claim.id for u in updates] == [first.id, second.id]
    # A 2ª chamada recebe a afirmação já extraída e a frase anterior como contexto.
    assert "A inflação caiu." in client.calls[1][1]["content"]
    assert "[0]" in client.calls[1][1]["content"].split("NOVAS FRASES")[0]


async def test_segments_arriving_during_a_call_are_batched(store: ClaimStore) -> None:
    empty = ExtractionResult(claims=[], last_sentence_incomplete=False)
    client = FakeClient([empty, empty], delay=0.1)
    pipe = make_pipeline(store, client, [])
    pipe.start()
    pipe.submit(seg(0, "Primeira frase."))
    await asyncio.sleep(0.02)  # 1ª chamada em andamento
    for i in range(1, 4):
        pipe.submit(seg(i, f"Frase {i}.", i * 2000))
    await pipe.close()
    assert len(client.calls) == 2
    new_part = client.calls[1][1]["content"].split("NOVAS FRASES:")[1]
    assert "[1]" in new_part and "[3]" in new_part


async def test_incomplete_last_sentence_is_resent(store: ClaimStore) -> None:
    client = FakeClient(
        [
            ExtractionResult(claims=[], last_sentence_incomplete=True),
            ExtractionResult(claims=[], last_sentence_incomplete=False),
        ]
    )
    pipe = make_pipeline(store, client, [])
    pipe.start()
    pipe.submit(seg(0, "O desemprego entre os jovens"))
    await asyncio.sleep(0.05)
    pipe.submit(seg(1, "é o maior da história.", 2000))
    await pipe.close()
    new_part = client.calls[1][1]["content"].split("NOVAS FRASES:")[1]
    assert "[0]" in new_part and "[1]" in new_part


async def test_llm_failure_reports_status_and_keeps_going(store: ClaimStore) -> None:
    client = FakeClient(
        [
            LlmError("Ollama fora do ar"),
            ExtractionResult(
                claims=[ExtractedClaim(segment_index=1, source_text="caiu", claim="X caiu.")],
                last_sentence_incomplete=False,
            ),
        ]
    )
    events: list[Any] = []
    pipe = make_pipeline(store, client, events)
    pipe.start()
    pipe.submit(seg(0, "Algo."))
    await asyncio.sleep(0.05)
    pipe.submit(seg(1, "X caiu.", 1000))
    await pipe.close()
    states = [(e.state, e.message) for e in events if e.type == "extractor.status"]
    assert ("error", "Ollama fora do ar") in states
    assert states[-1] == ("idle", None)
    assert len(store.for_session("s1")) == 1


async def test_manual_claim_uses_normalized_text(store: ClaimStore) -> None:
    from rtfc.claims import Anchor, manual_claim

    segments = [seg(0, "Ele disse que a fábrica fechou em março.")]
    client = FakeClient(
        [NormalizedClaim(claim="O ministro disse que a fábrica fechou em março.", verifiable=True)]
    )
    where = Anchor(0, 0, 0, 7, segments[0].start_ms, segments[0].end_ms)
    import datetime

    claim = await manual_claim(
        "s1", segments, where, client=client, store=store, language="pt",  # type: ignore[arg-type]
        when=datetime.date(2026, 10, 19),
    )  # fmt: skip
    assert claim.origin == "manual"
    assert claim.text.startswith("O ministro")
    assert claim.source_text == "Ele disse que a fábrica fechou em março."
    assert "2026-10-19" in client.calls[0][0]["content"]
