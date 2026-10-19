"""Baixa páginas e extrai o texto principal (trafilatura), com limites de tempo e tamanho."""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

MAX_BYTES = 3 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 rtfc/0.1"
)


async def fetch_text(url: str, *, timeout_s: float = 8.0) -> str | None:
    """Texto principal da página, ou None (erro, paywall, não-HTML, vazio)."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"},
        ) as http:
            async with http.stream("GET", url) as r:
                if r.status_code >= 400:
                    return None
                ctype = r.headers.get("content-type", "")
                if "html" not in ctype and "xml" not in ctype:
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                html = b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, UnicodeError) as exc:
        log.debug("fetch %s falhou: %s", url, exc)
        return None
    return await asyncio.to_thread(_extract, html, url)


def _extract(html: str, url: str) -> str | None:
    import trafilatura

    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=True, favor_precision=True
    )
    return text.strip() if text and len(text.strip()) > 200 else None
