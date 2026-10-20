"""Rechecagem com o modelo de qualidade depois da sessão (M6.1, ADR 0007).

Ao vivo, num Mac de 16 GB, só um LLM pequeno cabe junto com o Whisper. Depois que a
sessão acaba, este serviço tira o Whisper e o modelo rápido da memória e recheca as
afirmações com o "revisor" (por padrão qwen3:14b), uma por vez. O resultado fica ao lado
do da sessão (`pass = review`), e o card mostra o que mudou.

- Uma revisão por vez (as outras sessões esperam na fila).
- Pausa durante sessões ao vivo: a afirmação em andamento é refeita ao retomar.
- Espera as checagens rápidas da afirmação terminarem antes de revisá-la.
"""

import asyncio
import contextlib
import logging
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from rtfc.config import SecretStore, SettingsStore
from rtfc.factcheck.pipeline import Stage, check_claim
from rtfc.factcheck.service import CheckService, SessionContext
from rtfc.llm import LlmClient, LlmError
from rtfc.llm.ollama import unload as ollama_unload
from rtfc.protocol import ReviewStatus
from rtfc.search.base import SearchError
from rtfc.storage import CheckStore, ClaimStore, StoredCheck, StoredClaim, StoredSource
from rtfc.stt.service import SttService

log = logging.getLogger(__name__)

Scope = Literal["all", "pending", "doubtful"]
Broadcast = Callable[[BaseModel], Awaitable[None]]

DEFAULT_SECONDS = {"local": 65, "online": 10}
"""Estimativa por afirmação antes de haver medições (ADR 0007)."""
WAIT_LIVE_CHECK_S = 1.0


@dataclass
class _Run:
    session_id: str
    ids: list[str]
    total: int
    done: int = 0
    durations: list[float] = field(default_factory=list)
    state: str = "running"
    message: str | None = None


class ReviewService:
    def __init__(
        self,
        *,
        claims: ClaimStore,
        checks: CheckStore,
        check_service: CheckService,
        settings: SettingsStore,
        secrets: SecretStore,
        broadcast: Broadcast,
        session_context: SessionContext,
        stt: SttService | None,
    ) -> None:
        self._claims = claims
        self._checks = checks
        self._check_service = check_service
        self._settings = settings
        self._secrets = secrets
        self._broadcast = broadcast
        self._context = session_context
        self._stt = stt
        self._runs: dict[str, _Run] = {}
        self._order: list[str] = []
        self._worker: asyncio.Task[None] | None = None
        self._current: tuple[str, str, asyncio.Task[None]] | None = None
        self._allowed = asyncio.Event()
        self._allowed.set()
        self._prepared = False

    # --- API ----------------------------------------------------------------

    @property
    def model(self) -> str:
        r = self._settings.settings.reviewer
        return f"{r.provider}:{r.model}"

    def _is_local(self) -> bool:
        return self._settings.settings.reviewer.provider == "ollama"

    def status(self, session_id: str, request_id: str | None = None) -> ReviewStatus:
        run = self._runs.get(session_id)
        if run is None:
            return ReviewStatus(
                id=request_id, session_id=session_id, state="idle", model=self.model
            )
        state = "paused" if run.state == "running" and not self._allowed.is_set() else run.state
        remaining = run.total - run.done
        per = (
            statistics.median(run.durations)
            if run.durations
            else DEFAULT_SECONDS["local" if self._is_local() else "online"]
        )
        return ReviewStatus(
            id=request_id,
            session_id=session_id,
            state=state,  # type: ignore[arg-type]
            done=run.done,
            total=run.total,
            eta_s=round(per * remaining) if remaining else 0,
            model=self.model,
            message=run.message,
        )

    def select(self, session_id: str, scope: Scope) -> list[StoredClaim]:
        out = []
        for c in self._claims.for_session(session_id):
            if c.status == "discarded" or c.dedup_of:
                continue  # repetidas acompanham a original
            if scope == "pending" and c.review_status == "done":
                continue
            if scope == "doubtful":
                live = self._checks.get(c.id, "live")
                doubtful = c.status in ("error", "cancelled") or (
                    live is not None and live.verdict in ("inconclusivo", "fora_de_contexto")
                )
                if not doubtful:
                    continue
            out.append(c)
        return out

    async def start(self, session_id: str, scope: Scope = "pending") -> ReviewStatus:
        if session_id in self._runs and self._runs[session_id].state in ("running", "preparing"):
            return self.status(session_id)
        claims = self.select(session_id, scope)
        run = _Run(session_id, [c.id for c in claims], len(claims))
        if not claims:
            run.state = "done"
            run.message = "nada para rechecar"
            self._runs[session_id] = run
            await self._publish(session_id)
            return self.status(session_id)
        for c in claims:
            updated = self._claims.with_review_status(c.id, "queued")
            if updated:
                await self._check_service.emit(updated)
        self._runs[session_id] = run
        self._order.append(session_id)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._work())
        await self._publish(session_id)
        return self.status(session_id)

    async def cancel(self, session_id: str) -> ReviewStatus:
        run = self._runs.get(session_id)
        if run is None or run.state not in ("running", "preparing"):
            return self.status(session_id)
        run.state = "cancelled"
        if self._current and self._current[0] == session_id:
            self._current[2].cancel()
        for cid in run.ids:
            claim = self._claims.get(cid)
            if claim and claim.review_status in ("queued", "checking"):
                updated = self._claims.with_review_status(cid, "cancelled")
                if updated:
                    await self._check_service.emit(updated)
        run.ids = []
        await self._publish(session_id)
        return self.status(session_id)

    async def pause(self) -> None:
        """Sessão ao vivo começou: devolve a memória para o Whisper e o modelo rápido."""
        if not self._allowed.is_set():
            return
        self._allowed.clear()
        if self._current:
            self._current[2].cancel()  # a afirmação volta para a fila e é refeita ao retomar
        self._prepared = False
        if self._is_local():
            await ollama_unload(self._settings.settings.reviewer.model, self._base_url())
        for sid in self._order:
            await self._publish(sid)

    async def resume(self) -> None:
        if self._allowed.is_set():
            return
        self._allowed.set()
        for sid in self._order:
            await self._publish(sid)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(BaseException):
                await self._worker

    def busy(self) -> bool:
        return any(r.state in ("running", "preparing") for r in self._runs.values())

    # --- Internos -------------------------------------------------------------

    def _base_url(self) -> str | None:
        return self._settings.settings.reviewer.base_url

    async def _publish(self, session_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._broadcast(self.status(session_id))

    async def _prepare(self, run: _Run) -> None:
        """Libera a memória para o revisor: Whisper e modelos rápidos do Ollama."""
        if self._prepared:
            return
        run.state = "preparing"
        await self._publish(run.session_id)
        if self._stt is not None:
            await self._stt.unload()
        reviewer = self._settings.settings.reviewer
        if self._is_local():
            settings = self._settings.settings
            fast = {
                (r.model, r.base_url)
                for r in (settings.extractor, settings.checker)
                if r.provider == "ollama" and r.model != reviewer.model
            }
            for model, base_url in sorted(fast, key=lambda m: m[0]):
                await ollama_unload(model, base_url)
        self._prepared = True
        run.state = "running"
        await self._publish(run.session_id)

    async def _cleanup(self) -> None:
        if self._is_local() and self._allowed.is_set():
            await ollama_unload(self._settings.settings.reviewer.model, self._base_url())
        self._prepared = False

    async def _work(self) -> None:
        while self._order:
            sid = self._order[0]
            run = self._runs[sid]
            while run.ids and run.state != "cancelled":
                await self._allowed.wait()
                await self._prepare(run)
                cid = run.ids[0]
                task = asyncio.create_task(self._review(cid))
                self._current = (sid, cid, task)
                t0 = time.perf_counter()
                try:
                    await task
                except asyncio.CancelledError:
                    if task.cancelled() and run.state != "cancelled":
                        continue  # pausa: refaz a mesma afirmação ao retomar
                    if not task.cancelled():
                        raise
                    break
                finally:
                    self._current = None
                run.ids.pop(0)
                run.done += 1
                run.durations.append(time.perf_counter() - t0)
                await self._publish(sid)
            if run.state != "cancelled":
                run.state = "done"
                log.info("revisão de %s: %d afirmações com %s", sid, run.done, self.model)
            self._order.pop(0)
            await self._publish(sid)
        await self._cleanup()

    async def _wait_live_check(self, claim_id: str) -> StoredClaim | None:
        while True:
            claim = self._claims.get(claim_id)
            if claim is None or claim.status not in ("queued", "checking"):
                return claim
            await asyncio.sleep(WAIT_LIVE_CHECK_S)

    async def _review(self, claim_id: str) -> None:
        claim = await self._wait_live_check(claim_id)
        if claim is None or claim.status == "discarded":
            return
        ctx = self._context(claim.session_id, claim.start_ms, claim.end_ms)
        settings = self._settings.settings
        stages = self._check_service.stages

        async def on_stage(stage: Stage) -> None:
            stages[claim_id] = stage
            current = self._claims.get(claim_id)
            if current:
                await self._check_service.emit(current)

        checking = self._claims.with_review_status(claim_id, "checking")
        if checking:
            await self._check_service.emit(checking)
        try:
            outcome = await check_claim(
                claim.text,
                client=LlmClient(settings.reviewer, self._secrets, timeout_s=300),
                search_settings=settings.search,
                secrets=self._secrets,
                language=ctx.language,
                when=ctx.when,
                on_stage=on_stage,
                claim_context=claim.context,
                content_context=ctx.content,
                speaker=claim.speaker,
                transcript=ctx.transcript,
                full_evidence=True,
            )
        except asyncio.CancelledError:
            stages.pop(claim_id, None)
            # Pausa: volta para a fila. Se a revisão foi cancelada, o cancel() já marcou.
            current = self._claims.get(claim_id)
            if current and current.review_status == "checking":
                queued = self._claims.with_review_status(claim_id, "queued")
                if queued:
                    with contextlib.suppress(Exception):
                        await self._check_service.emit(queued)
            raise
        except (LlmError, SearchError, ValueError) as exc:
            log.warning("revisão de %s falhou: %s", claim_id, exc)
            stages.pop(claim_id, None)
            failed = self._claims.with_review_status(claim_id, "error")
            if failed:
                await self._check_service.emit(failed)
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
            ),
            "review",
        )
        stages.pop(claim_id, None)
        done = self._claims.with_review_status(claim_id, "done")
        if done:
            await self._check_service.emit(done)
        for dup in self._claims.duplicates_of(claim_id):
            await self._check_service.emit(dup)
