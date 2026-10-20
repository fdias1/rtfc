"""Extração contínua de afirmações de uma sessão.

A cada segmento confirmado o extrator roda sobre as frases novas (+ ~60 s de contexto).
Frases que chegam enquanto uma chamada está em andamento são agrupadas na próxima
(no máximo uma chamada em andamento por sessão). Se o modelo disser que a última frase
ficou cortada, ela é reenviada junto com a seguinte.
"""

import asyncio
import contextlib
import logging
import re
import secrets
import time
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from pydantic import BaseModel
from rapidfuzz import fuzz

from rtfc.claims.anchor import Anchor, anchor, whole_segment, words_between
from rtfc.claims.extractor import extract_claims, generate_context, normalize_excerpt
from rtfc.llm import LlmClient, LlmConfigError, LlmError
from rtfc.protocol import (
    CheckData,
    CheckSourceData,
    ClaimData,
    ClaimUpdated,
    ExtractorStatus,
)
from rtfc.storage import ClaimStore, StoredCheck, StoredClaim, StoredSegment

log = logging.getLogger(__name__)

CONTEXT_MS = 60_000
AUTO_CONTEXT_AT = (6, 40)
"""Contexto automático: gerado com 6 frases e atualizado com 40 (se não veio do usuário)."""
MAX_BATCH = 8
DEDUP_THRESHOLD = 88
"""Similaridade (0–100, token_set_ratio) a partir da qual duas afirmações são a mesma."""

Emit = Callable[[BaseModel], Awaitable[None]]
ClientFactory = Callable[[], LlmClient]


def _norm_claim(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", text)


def find_duplicate(text: str, existing: list[StoredClaim]) -> StoredClaim | None:
    target = _norm_claim(text)
    for claim in existing:
        if claim.dedup_of is None and claim.status != "discarded":
            if fuzz.token_set_ratio(target, _norm_claim(claim.text)) >= DEDUP_THRESHOLD:
                return claim
    return None


def to_check_data(c: StoredCheck) -> CheckData:
    return CheckData(
        verdict=c.verdict,  # type: ignore[arg-type]
        confidence=c.confidence,
        justification=c.justification,
        sources=[CheckSourceData.model_validate(s.__dict__) for s in c.sources],
        model=c.model,
        search_provider=c.search_provider,
        queries=list(c.queries),
        checked_at=c.checked_at,
        duration_ms=c.duration_ms,
    )


def to_claim_data(
    c: StoredClaim,
    check: StoredCheck | None = None,
    stage: str | None = None,
    *,
    reviewed: bool = False,
    previous_verdict: str | None = None,
) -> ClaimData:
    return ClaimData(
        id=c.id,
        session_id=c.session_id,
        origin="manual" if c.origin == "manual" else "auto",
        text=c.text,
        source_text=c.source_text,
        from_segment=c.from_segment,
        from_word=c.from_word,
        to_segment=c.to_segment,
        to_word=c.to_word,
        start_ms=c.start_ms,
        end_ms=c.end_ms,
        status=c.status,  # type: ignore[arg-type]
        dedup_of=c.dedup_of,
        speaker=c.speaker,
        context=c.context,
        stage=stage  # type: ignore[arg-type]
        if c.status == "checking" or c.review_status == "checking"
        else None,
        check=to_check_data(check) if check else None,
        error=c.error,
        reviewed=reviewed,
        previous_verdict=previous_verdict,  # type: ignore[arg-type]
        review_status=c.review_status,  # type: ignore[arg-type]
    )


def new_claim(
    session_id: str,
    *,
    origin: str,
    text: str,
    source_text: str,
    where: Anchor,
    existing: list[StoredClaim],
    speaker: str | None,
    model: str | None,
    context: str | None = None,
    score: int | None = None,
) -> StoredClaim:
    dup = find_duplicate(text, existing)
    return StoredClaim(
        id=secrets.token_hex(6),
        session_id=session_id,
        origin=origin,
        text=text.strip(),
        source_text=source_text.strip(),
        from_segment=where.from_segment,
        from_word=where.from_word,
        to_segment=where.to_segment,
        to_word=where.to_word,
        start_ms=where.start_ms,
        end_ms=where.end_ms,
        status=dup.status if dup else "queued",
        dedup_of=dup.id if dup else None,
        speaker=speaker,
        created_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
        model=model,
        context=(context or "").strip() or None,
        score=score,
    )


class ClaimPipeline:
    def __init__(
        self,
        session_id: str,
        *,
        client_factory: ClientFactory,
        store: ClaimStore,
        emit: Emit,
        language: Callable[[], str | None],
        when: date | None = None,
        on_claim: Callable[[StoredClaim], None] | None = None,
        content_context: Callable[[], str | None] = lambda: None,
        min_score: Callable[[], int] = lambda: 1,
        on_auto_context: Callable[[str], Awaitable[object]] | None = None,
        auto_context_allowed: Callable[[], bool] = lambda: True,
    ) -> None:
        self.session_id = session_id
        self._on_claim = on_claim
        self._content_context = content_context
        self._min_score = min_score
        self._on_auto_context = on_auto_context
        self._auto_context_allowed = auto_context_allowed
        self.skipped_low_score = 0
        self._client_factory = client_factory
        self._store = store
        self._emit = emit
        self._language = language
        self._when = when or date.today()
        self.segments: list[StoredSegment] = []
        self._pending: list[StoredSegment] = []
        self._carry: StoredSegment | None = None
        self._received_at: dict[int, float] = {}
        self._wake = asyncio.Event()
        self._closing = False
        self._state: tuple[str, str | None] = ("idle", None)
        self.latencies_ms: list[int] = []
        self._task: asyncio.Task[None] | None = None
        self._auto_done: set[int] = set()

    # --- API ----------------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def submit(self, segment: StoredSegment) -> None:
        self.segments.append(segment)
        self._pending.append(segment)
        self._received_at[segment.index] = time.monotonic()
        self._wake.set()

    async def close(self) -> None:
        """Processa o que falta (inclusive a frase "cortada") e encerra."""
        self._closing = True
        self._wake.set()
        if self._task:
            with contextlib.suppress(Exception):
                await self._task

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()

    @property
    def claims(self) -> list[StoredClaim]:
        return self._store.for_session(self.session_id)

    # --- Loop ---------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._pending or (self._closing and self._carry):
                batch = ([self._carry] if self._carry else []) + self._pending[:MAX_BATCH]
                self._pending = self._pending[MAX_BATCH:]
                self._carry = None
                await self._maybe_auto_context()
                await self._extract(batch, final=self._closing and not self._pending)
            if self._closing:
                return

    async def _maybe_auto_context(self) -> None:
        n = len(self.segments)
        due = [t for t in AUTO_CONTEXT_AT if n >= t and t not in self._auto_done]
        if not due or self._on_auto_context is None or not self._auto_context_allowed():
            return
        self._auto_done.update(due)
        try:
            result = await generate_context(
                self._client_factory(),
                segments=self.segments,
                language=self._language(),
                when=self._when,
                hint=self._content_context(),
            )
        except (LlmConfigError, LlmError, ValueError) as exc:
            log.warning("contexto automático falhou: %s", exc)
            return
        await self._on_auto_context(result.value.context.strip())

    async def _set_state(self, state: str, message: str | None = None) -> None:
        if (state, message) == self._state:
            return
        self._state = (state, message)
        await self._emit(
            ExtractorStatus(session_id=self.session_id, state=state, message=message)  # type: ignore[arg-type]
        )

    async def _extract(self, batch: list[StoredSegment], *, final: bool) -> None:
        first = batch[0]
        context = [
            s
            for s in self.segments
            if s.index < first.index and s.end_ms >= first.start_ms - CONTEXT_MS
        ]
        existing = self.claims
        try:
            client = self._client_factory()
            await self._set_state("running")
            result = await extract_claims(
                client,
                new=batch,
                context=context,
                already=[c.text for c in existing if c.status != "discarded"],
                language=self._language(),
                when=self._when,
                content_context=self._content_context(),
            )
        except asyncio.CancelledError:
            raise
        except (LlmConfigError, LlmError, ValueError) as exc:
            log.warning("extração falhou: %s", exc)
            await self._set_state("error", str(exc))
            return

        by_index = {s.index: s for s in batch}
        min_score = self._min_score()
        for item in result.value.claims:
            seg = by_index.get(item.segment_index)
            if seg is None:
                continue  # o modelo apontou para o contexto: ignorado
            if item.score < min_score:
                # Vaga ou irrelevante demais para valer uma checagem (ADR 0006).
                self.skipped_low_score += 1
                log.info("afirmação com nota %d ignorada: %s", item.score, item.claim)
                continue
            # A afirmação pode continuar no segmento seguinte do lote.
            nearby = [s for s in batch if seg.index <= s.index <= seg.index + 1]
            where = anchor(item.source_text, nearby) or whole_segment(seg)
            claim = new_claim(
                self.session_id,
                origin="auto",
                text=item.claim,
                source_text=item.source_text,
                where=where,
                existing=existing,
                speaker=seg.speaker,
                model=result.model,
                context=item.context,
                score=item.score,
            )
            self._store.upsert(claim)
            existing.append(claim)
            received = self._received_at.get(seg.index)
            if received is not None:
                self.latencies_ms.append(round((time.monotonic() - received) * 1000))
            await self._emit(ClaimUpdated(claim=to_claim_data(claim)))
            if self._on_claim:
                self._on_claim(claim)

        if result.value.last_sentence_incomplete and not final:
            self._carry = batch[-1]
        await self._set_state("idle")

    # --- Manual ---------------------------------------------------------------

    async def manual(self, where: Anchor) -> StoredClaim:
        return await manual_claim(
            self.session_id,
            self.segments,
            where,
            client=self._client_factory(),
            store=self._store,
            language=self._language(),
            when=self._when,
            content_context=self._content_context(),
        )


async def manual_claim(
    session_id: str,
    segments: list[StoredSegment],
    where: Anchor,
    *,
    client: LlmClient,
    store: ClaimStore,
    language: str | None,
    when: date,
    content_context: str | None = None,
) -> StoredClaim:
    excerpt = words_between(segments, where)
    if not excerpt:
        raise ValueError("trecho vazio")
    context = [
        s
        for s in segments
        if s.end_ms >= where.start_ms - CONTEXT_MS and s.start_ms <= where.end_ms + 10_000
    ]
    result = await normalize_excerpt(
        client,
        excerpt=excerpt,
        context=context,
        language=language,
        when=when,
        content_context=content_context,
    )
    seg = next((s for s in segments if s.index == where.from_segment), None)
    claim = new_claim(
        session_id,
        origin="manual",
        text=result.value.claim,
        source_text=excerpt,
        where=where,
        existing=store.for_session(session_id),
        speaker=seg.speaker if seg else None,
        model=result.model,
    )
    store.upsert(claim)
    return claim
