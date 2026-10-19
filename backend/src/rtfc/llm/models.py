"""Lista os modelos disponíveis num provedor (para o seletor da UI)."""

import httpx

from rtfc.config import SecretStore, get_provider

# Famílias que não servem para conversa/JSON (áudio, imagem, embeddings…).
_SKIP = (
    "audio", "realtime", "tts", "transcribe", "image", "search", "embedding", "moderation",
    "dall", "whisper", "davinci", "babbage", "sora", "codex", "instruct",
)  # fmt: skip


async def list_models(
    provider_id: str, secrets: SecretStore, base_url: str | None = None
) -> list[str]:
    provider = get_provider(provider_id)
    url = base_url or provider.default_base_url
    async with httpx.AsyncClient(timeout=10) as http:
        if provider.id == "ollama":
            r = await http.get(f"{url}/api/tags")
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
        if provider.id in ("openai", "openai_compatible"):
            key = secrets.get(provider.id)
            root = (url or "https://api.openai.com").rstrip("/")
            if not root.endswith("/v1"):
                root += "/v1"
            r = await http.get(
                f"{root}/models", headers={"Authorization": f"Bearer {key}"} if key else {}
            )
            r.raise_for_status()
            ids = [m["id"] for m in r.json().get("data", [])]
            if provider.id == "openai":
                ids = [
                    i for i in ids if i.startswith(("gpt-", "o")) and not any(s in i for s in _SKIP)
                ]
            return sorted(ids)
    return list(provider.suggested_models)
