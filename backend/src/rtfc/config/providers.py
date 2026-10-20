"""Provedores de LLM suportados e como chegar neles pelo LiteLLM."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    litellm_prefix: str
    needs_key: bool
    default_base_url: str | None = None
    suggested_models: tuple[str, ...] = ()


PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in (
        Provider(
            "openai", "OpenAI", "openai/", True, None, ("gpt-5.4-mini", "gpt-5.4", "gpt-5.4-nano")
        ),
        Provider(
            "ollama",
            "Ollama (local)",
            "ollama_chat/",
            False,
            "http://127.0.0.1:11434",
            ("qwen3:8b", "qwen3:14b", "gemma3:12b"),
        ),
        Provider(
            "anthropic",
            "Anthropic (Claude)",
            "anthropic/",
            True,
            None,
            ("claude-sonnet-5-5", "claude-haiku-5-5"),
        ),
        Provider(
            "gemini", "Google Gemini", "gemini/", True, None, ("gemini-2.5-flash", "gemini-2.5-pro")
        ),
        Provider("deepseek", "DeepSeek", "deepseek/", True, None, ("deepseek-chat",)),
        Provider(
            "mistral",
            "Mistral",
            "mistral/",
            True,
            None,
            ("mistral-small-latest", "mistral-large-latest"),
        ),
        Provider("openai_compatible", "Compatível com OpenAI (URL própria)", "openai/", False),
    )
}


FAKE = Provider("fake", "Falso (testes)", "fake/", False)


def get_provider(provider_id: str) -> Provider:
    from rtfc.llm.fake import fake_enabled

    if provider_id == FAKE.id and fake_enabled():
        return FAKE
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(f"provedor desconhecido: {provider_id}") from None
