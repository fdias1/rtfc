"""Controle de memória do Ollama: descarregar um modelo da GPU na hora (keep_alive = 0)."""

import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:11434"


async def unload(model: str, base_url: str | None = None) -> bool:
    url = (base_url or DEFAULT_URL).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0})
            ok = r.status_code < 400
    except httpx.HTTPError as exc:
        log.info("não foi possível descarregar %s do Ollama: %s", model, exc)
        return False
    if ok:
        log.info("modelo %s descarregado do Ollama", model)
    return ok
