"""Baixa páginas e extrai o texto principal (trafilatura), com limites de tempo e tamanho."""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)
# O pypdf avisa de cada fonte que não sabe decodificar; o texto sai mesmo assim.
logging.getLogger("pypdf").setLevel(logging.ERROR)

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
                is_pdf = "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf")
                if not is_pdf and "html" not in ctype and "xml" not in ctype:
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                body = b"".join(chunks)
                if is_pdf:
                    return await asyncio.to_thread(_extract_pdf, body)
                html = body.decode(r.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, UnicodeError) as exc:
        log.debug("fetch %s falhou: %s", url, exc)
        return None
    return await asyncio.to_thread(_extract, html, url)


MAX_PDF_PAGES = 25


def _extract_pdf(data: bytes) -> str | None:
    """Relatórios e notas técnicas oficiais muitas vezes só existem em PDF."""
    import io

    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages[:MAX_PDF_PAGES]]
    except Exception as exc:  # PDF truncado (limite de tamanho), criptografado…
        log.debug("PDF ilegível: %s", exc)
        return None
    text = "\n".join(pages).strip()
    return text if len(text) > 200 else None


def _extract(html: str, url: str) -> str | None:
    import trafilatura

    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=True, favor_precision=True
    )
    return text.strip() if text and len(text.strip()) > 200 else None
