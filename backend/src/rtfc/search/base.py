"""Tipos comuns da busca."""

from dataclasses import dataclass, field, replace
from typing import Literal, Protocol
from urllib.parse import urlsplit

Tier = Literal["factchecker", "official", "press", "other"]


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    provider: str
    content: str | None = None
    """Texto principal da página (quando o provedor já entrega ou depois do fetch)."""
    published: str | None = None
    tier: Tier = "other"
    queries: tuple[str, ...] = field(default=())

    @property
    def domain(self) -> str:
        host = urlsplit(self.url).hostname or ""
        return host.removeprefix("www.")

    def with_(self, **changes: object) -> "SearchResult":
        return replace(self, **changes)  # type: ignore[arg-type]


class SearchError(RuntimeError):
    pass


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, *, language: str | None, limit: int) -> list[SearchResult]:
        """Uma consulta. Levanta SearchError se o provedor estiver indisponível."""
        ...
