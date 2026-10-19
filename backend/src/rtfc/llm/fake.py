"""LLM falso e determinístico para testes E2E (só existe com RTFC_TEST_FAKE_LLM=1).

- Extração: cada frase nova com 4+ palavras vira uma afirmação (o texto da própria frase).
- Normalização de trecho: devolve o trecho.
- Teste de conexão: ok.
"""

import os
import re
from typing import Any

from pydantic import BaseModel

FAKE_PROVIDER = "fake"


def fake_enabled() -> bool:
    return os.environ.get("RTFC_TEST_FAKE_LLM") == "1"


def fake_reply(messages: list[dict[str, str]], schema: type[BaseModel]) -> BaseModel:
    user = messages[-1]["content"]
    fields = set(schema.model_fields)
    if {"claims", "last_sentence_incomplete"} <= fields:
        new = user.split("NOVAS FRASES:", 1)[1].split("AFIRMAÇÕES JÁ EXTRAÍDAS", 1)[0]
        claims: list[dict[str, Any]] = []
        for m in re.finditer(r"^\[(\d+)\](?: \([^)]*\))? (.+)$", new, re.M):
            text = m.group(2).strip()
            if len(text.split()) >= 4:
                claims.append(
                    {"segment_index": int(m.group(1)), "source_text": text, "claim": text}
                )
        return schema.model_validate({"claims": claims, "last_sentence_incomplete": False})
    if {"claim", "verifiable"} <= fields:
        excerpt = user.split("TRECHO:", 1)[1].strip()
        return schema.model_validate({"claim": excerpt, "verifiable": True})
    return schema.model_validate({"ok": True})
