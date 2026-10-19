"""Provedores de busca: SearXNG (padrão, local), DuckDuckGo (reserva sem conta) e Tavily."""

import asyncio
import logging

import httpx

from rtfc.search.base import SearchError, SearchResult

log = logging.getLogger(__name__)

LANG_CODES = {"pt": "pt-BR", "en": "en-US", "es": "es-ES"}
DDG_REGIONS = {"pt": "br-pt", "en": "us-en", "es": "es-es"}


class SearxngProvider:
    name = "searxng"

    def __init__(self, base_url: str = "http://127.0.0.1:8888", timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    async def search(self, query: str, *, language: str | None, limit: int) -> list[SearchResult]:
        params = {"q": query, "format": "json", "safesearch": "0"}
        if language:
            params["language"] = LANG_CODES.get(language, language)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                r = await http.get(f"{self.base_url}/search", params=params)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchError(f"SearXNG indisponível em {self.base_url}: {exc}") from exc
        return [
            SearchResult(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("content") or "",
                provider=self.name,
                published=item.get("publishedDate"),
            )
            for item in data.get("results", [])[:limit]
            if item.get("url", "").startswith(("http://", "https://"))
        ]

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as http:
                r = await http.get(f"{self.base_url}/healthz")
                return r.status_code == 200
        except httpx.HTTPError:
            return False


class DuckDuckGoProvider:
    """Sem conta e sem chave, mas não oficial: sujeito a bloqueios por excesso de buscas."""

    name = "duckduckgo"

    async def search(self, query: str, *, language: str | None, limit: int) -> list[SearchResult]:
        from ddgs import DDGS

        region = DDG_REGIONS.get(language or "", "wt-wt")

        def run() -> list[dict[str, str]]:
            return list(DDGS().text(query, region=region, max_results=limit) or [])

        try:
            items = await asyncio.to_thread(run)
        except Exception as exc:
            raise SearchError(f"DuckDuckGo falhou: {exc}") from exc
        return [
            SearchResult(
                url=i["href"],
                title=i.get("title", ""),
                snippet=i.get("body", ""),
                provider=self.name,
            )
            for i in items
            if i.get("href", "").startswith(("http://", "https://"))
        ]


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key: str, timeout_s: float = 20.0) -> None:
        self._key = api_key
        self._timeout = timeout_s

    async def search(self, query: str, *, language: str | None, limit: int) -> list[SearchResult]:
        body = {
            "query": query,
            "max_results": limit,
            "search_depth": "advanced",
            "include_raw_content": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                r = await http.post(
                    "https://api.tavily.com/search",
                    json=body,
                    headers={"Authorization": f"Bearer {self._key}"},
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchError(f"Tavily falhou: {exc}") from exc
        return [
            SearchResult(
                url=i["url"],
                title=i.get("title", ""),
                snippet=i.get("content", ""),
                provider=self.name,
                content=i.get("raw_content") or None,
                published=i.get("published_date"),
            )
            for i in data.get("results", [])
        ]
