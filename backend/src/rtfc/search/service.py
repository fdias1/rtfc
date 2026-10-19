"""Busca com o provedor configurado e reserva automática no DuckDuckGo."""

import asyncio
import logging
import time
from dataclasses import dataclass

from rtfc.config import SearchSettings, SecretStore
from rtfc.search.base import SearchError, SearchProvider, SearchResult
from rtfc.search.providers import DuckDuckGoProvider, SearxngProvider, TavilyProvider

log = logging.getLogger(__name__)

PER_QUERY = 8
MAX_CONCURRENT_QUERIES = 2
MIN_INTERVAL_S = 0.4
"""Ritmo das consultas: os buscadores bloqueiam rajadas (CAPTCHA, "too many requests")."""
CACHE_TTL_S = 3600

_limiter: asyncio.Semaphore | None = None
_last_start = 0.0
_cache: dict[tuple[str, str, str | None], tuple[float, list[SearchResult]]] = {}


def _semaphore() -> asyncio.Semaphore:
    global _limiter
    if _limiter is None:
        _limiter = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)
    return _limiter


async def _paced(provider: SearchProvider, query: str, language: str | None) -> list[SearchResult]:
    global _last_start
    key = (provider.name, query.strip().lower(), language)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
        return cached[1]
    async with _semaphore():
        wait = _last_start + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_start = time.monotonic()
        results = await provider.search(query, language=language, limit=PER_QUERY)
    if results:
        _cache[key] = (time.monotonic(), results)
    return results


@dataclass(frozen=True)
class SearchOutcome:
    results: list[SearchResult]
    provider: str
    """Provedor que respondeu (pode ser a reserva)."""
    warnings: list[str]


def make_provider(settings: SearchSettings, secrets: SecretStore) -> SearchProvider:
    from rtfc.llm.fake import FakeSearchProvider, fake_enabled

    if fake_enabled():
        return FakeSearchProvider()
    if settings.provider == "tavily":
        key = secrets.get("tavily")
        if not key:
            raise SearchError("chave da Tavily não configurada")
        return TavilyProvider(key)
    if settings.provider == "duckduckgo":
        return DuckDuckGoProvider()
    return SearxngProvider(settings.searxng_url)


async def _run(
    provider: SearchProvider, queries: list[str], language: str | None
) -> list[SearchResult]:
    batches = await asyncio.gather(
        *(_paced(provider, q, language) for q in queries),
        return_exceptions=True,
    )
    results: list[SearchResult] = []
    errors: list[BaseException] = []
    for q, batch in zip(queries, batches, strict=True):
        if isinstance(batch, BaseException):
            errors.append(batch)
            continue
        results.extend(r.with_(queries=(q,)) for r in batch)
    if errors and not results:
        raise SearchError(str(errors[0]))
    if not results:
        raise SearchError(f"{provider.name}: nenhum resultado para as consultas")
    return results


async def search(
    queries: list[str], *, language: str | None, settings: SearchSettings, secrets: SecretStore
) -> SearchOutcome:
    warnings: list[str] = []
    try:
        primary = make_provider(settings, secrets)
        return SearchOutcome(await _run(primary, queries, language), primary.name, warnings)
    except SearchError as exc:
        if not settings.fallback_duckduckgo or settings.provider == "duckduckgo":
            raise
        log.warning("busca principal falhou (%s); usando DuckDuckGo", exc)
        warnings.append(f"{exc} — usando DuckDuckGo como reserva")
    fallback = DuckDuckGoProvider()
    return SearchOutcome(await _run(fallback, queries, language), fallback.name, warnings)
