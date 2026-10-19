"""Fila de checagem do app: N workers, prioridade para pedidos manuais, cancelar e rechecar.

Os eventos vão para todas as conexões (`broadcast`): uma checagem pode terminar depois que
a sessão acabou, ou com outra sessão aberta na tela.
"""

import asyncio
import contextlib
import itertools
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from pydantic import BaseModel

from rtfc.claims.pipeline import to_claim_data
from rtfc.config import SecretStore, SettingsStore
from rtfc.factcheck.pipeline import Stage, check_claim
from rtfc.llm import LlmClient, LlmError
from rtfc.protocol import ClaimUpdated
from rtfc.search.base import SearchError
from rtfc.storage import CheckStore, ClaimStore, StoredCheck, StoredClaim, StoredSource

log = logging.getLogger(__name__)

PRIORITY_MANUAL = 0
PRIORITY_AUTO = 1

Broadcast = Callable[[BaseModel], Awaitable[None]]
SessionContext = Callable[[str], tuple[str | None, date]]
"""session_id → (idioma, data do discurso)."""


class CheckService:
    def __init__(
        self,
        *,
        claims: ClaimStore,
        checks: CheckStore,
        settings: SettingsStore,
        secrets: SecretStore,
        broadcast: Broadcast,
        session_context: SessionContext,
        speech_age: Callable[[str, int], int | None] | None = None,
    ) -> None:
        self._claims = claims
        self._checks = checks
        self._settings = settings
        self._secrets = secrets
        self._broadcast = broadcast
        self._context = session_context
        self._speech_age = speech_age
        self.end_to_end_ms: list[int] = []
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._queued: set[str] = set()
        self._running: dict[str, asyncio.Task[None]] = {}
        self._stage: dict[str, Stage] = {}
        self._workers: list[asyncio.Task[None]] = []
        self.durations_ms: list[int] = []

    # --- API ----------------------------------------------------------------

    def start(self) -> None:
        if self._workers:
            return
        n = self._settings.settings.check_concurrency
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(n)]

    async def stop(self) -> None:
        for t in [*self._workers, *self._running.values()]:
            t.cancel()
        for t in [*self._workers, *self._running.values()]:
            with contextlib.suppress(BaseException):
                await t
        self._workers = []

    def data(self, claim: StoredClaim) -> BaseModel:
        """ClaimData com o resultado (o da original, se for repetida) e a etapa atual."""
        source = claim.dedup_of or claim.id
        return to_claim_data(claim, self._checks.get(source), self._stage.get(claim.id))

    async def enqueue(self, claim: StoredClaim, *, priority: int = PRIORITY_AUTO) -> StoredClaim:
        if claim.id in self._queued or claim.id in self._running:
            return claim
        claim = claim.with_status("queued")
        self._claims.upsert(claim)
        self._queued.add(claim.id)
        self._queue.put_nowait((priority, next(self._seq), claim.id))
        self.start()
        await self._emit(claim)
        return claim

    async def cancel(self, claim_id: str) -> StoredClaim:
        claim = self._require(claim_id)
        task = self._running.get(claim_id)
        if task:
            task.cancel()  # aborta busca/LLM em andamento; o worker marca como cancelada
            return claim
        if claim_id in self._queued:
            self._queued.discard(claim_id)  # o worker pula ao tirar da fila
            claim = claim.with_status("cancelled")
            self._claims.upsert(claim)
            await self._emit(claim)
        return claim

    async def retry(self, claim_id: str) -> StoredClaim:
        claim = self._require(claim_id)
        if claim.dedup_of:
            # Repetida: rechecar é rechecar a original (o resultado é o mesmo).
            original = self._claims.get(claim.dedup_of)
            if original:
                await self.enqueue(original, priority=PRIORITY_MANUAL)
                return claim
        return await self.enqueue(claim, priority=PRIORITY_MANUAL)

    # --- Internos -------------------------------------------------------------

    def _require(self, claim_id: str) -> StoredClaim:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise ValueError(f"afirmação desconhecida: {claim_id}")
        return claim

    async def _emit(self, claim: StoredClaim) -> None:
        with contextlib.suppress(Exception):
            await self._broadcast(ClaimUpdated(claim=self.data(claim)))  # type: ignore[arg-type]

    async def _set(self, claim_id: str, status: str, error: str | None = None) -> None:
        claim = self._claims.get(claim_id)
        if claim is None or claim.status == "discarded":
            return  # descartada durante a checagem: o descarte prevalece
        claim = claim.with_status(status, error)
        self._claims.upsert(claim)
        await self._emit(claim)
        # As repetidas acompanham a original.
        for dup in self._claims.duplicates_of(claim_id):
            if dup.status != "discarded":
                dup = dup.with_status(status, error)
                self._claims.upsert(dup)
                await self._emit(dup)

    async def _worker(self, n: int) -> None:
        while True:
            _, _, claim_id = await self._queue.get()
            if claim_id not in self._queued:
                continue  # cancelada enquanto esperava
            self._queued.discard(claim_id)
            task = asyncio.create_task(self._check(claim_id))
            self._running[claim_id] = task
            try:
                await task
            except asyncio.CancelledError:
                if task.cancelled():
                    await self._set(claim_id, "cancelled")
                else:
                    raise
            finally:
                self._running.pop(claim_id, None)
                self._stage.pop(claim_id, None)

    async def _check(self, claim_id: str) -> None:
        claim = self._claims.get(claim_id)
        if claim is None or claim.status == "discarded":
            return
        language, when = self._context(claim.session_id)
        settings = self._settings.settings

        async def on_stage(stage: Stage) -> None:
            self._stage[claim_id] = stage
            await self._emit(self._claims.get(claim_id) or claim)

        await self._set(claim_id, "checking")
        try:
            outcome = await check_claim(
                claim.text,
                client=LlmClient(settings.checker, self._secrets),
                search_settings=settings.search,
                secrets=self._secrets,
                language=language,
                when=when,
                on_stage=on_stage,
            )
        except asyncio.CancelledError:
            raise
        except (LlmError, SearchError, ValueError) as exc:
            log.warning("checagem de %s falhou: %s", claim_id, exc)
            self._stage.pop(claim_id, None)
            await self._set(claim_id, "error", str(exc)[:300])
            return
        except Exception as exc:
            log.exception("checagem de %s falhou", claim_id)
            self._stage.pop(claim_id, None)
            await self._set(claim_id, "error", f"erro inesperado: {exc}"[:300])
            return

        v = outcome.verdict
        self._checks.save(
            StoredCheck(
                claim_id=claim_id,
                verdict=v.verdict,
                confidence=v.confidence,
                justification=v.justification,
                model=outcome.model,
                search_provider=outcome.search_provider,
                queries=tuple(outcome.queries),
                checked_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
                duration_ms=outcome.duration_ms,
                sources=tuple(
                    StoredSource(
                        url=s.result.url,
                        title=s.result.title,
                        domain=s.result.domain,
                        tier=s.result.tier,
                        stance=s.stance,
                        quote=s.quote,
                        published=s.result.published,
                    )
                    for s in v.sources
                ),
            )
        )
        self.durations_ms.append(outcome.duration_ms)
        age = self._speech_age(claim.session_id, claim.end_ms) if self._speech_age else None
        if age is not None:
            # Meta do PRD (RNF2b): fala → veredicto na UI ≤ 35 s (p90).
            self.end_to_end_ms.append(age)
            log.info(
                "fala → veredicto: %.1fs (checagem %.1fs)", age / 1000, outcome.duration_ms / 1000
            )
        self._stage.pop(claim_id, None)
        await self._set(claim_id, "done")
