"""Busca com o provedor configurado e reserva automática no DuckDuckGo."""

import asyncio
import logging
from dataclasses import dataclass

from rtfc.config import SearchSettings, SecretStore
from rtfc.search.base import SearchError, SearchProvider, SearchResult
from rtfc.search.providers import DuckDuckGoProvider, SearxngProvider, TavilyProvider

log = logging.getLogger(__name__)

PER_QUERY = 8


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
        *(provider.search(q, language=language, limit=PER_QUERY) for q in queries),
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
