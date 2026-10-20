"""LLM falso e determinístico para testes E2E (só existe com RTFC_TEST_FAKE_LLM=1).

- Extração: cada frase nova com 4+ palavras vira uma afirmação (o texto da própria frase).
- Normalização de trecho: devolve o trecho.
- Consultas: a própria afirmação. Veredicto: "verdadeiro", citando as evidências 1 e 2.
- Busca: `FakeSearchProvider`, 3 resultados com texto (sem rede).
- Teste de conexão: ok.
"""

import os
import re
from typing import Any

from pydantic import BaseModel

FAKE_PROVIDER = "fake"


def fake_enabled() -> bool:
    return os.environ.get("RTFC_TEST_FAKE_LLM") == "1"


def fake_reply(
    messages: list[dict[str, str]], schema: type[BaseModel], model: str = "fake"
) -> BaseModel:
    user = messages[-1]["content"]
    fields = set(schema.model_fields)
    if {"claims", "last_sentence_incomplete"} <= fields:
        new = user.split("NOVAS FRASES:", 1)[1].split("AFIRMAÇÕES JÁ EXTRAÍDAS", 1)[0]
        claims: list[dict[str, Any]] = []
        for m in re.finditer(r"^\[(\d+)\](?: \([^)]*\))? (.+)$", new, re.M):
            text = m.group(2).strip()
            if len(text.split()) >= 4:
                claims.append(
                    {
                        "segment_index": int(m.group(1)),
                        "source_text": text,
                        "claim": text,
                        "context": "Contexto de teste.",
                        "score": 5,
                    }
                )
        return schema.model_validate({"claims": claims, "last_sentence_incomplete": False})
    if {"claim", "verifiable"} <= fields:
        excerpt = user.split("TRECHO:", 1)[1].strip()
        return schema.model_validate({"claim": excerpt, "verifiable": True})
    if fields == {"context"}:
        return schema.model_validate({"context": "Conteúdo de teste gerado automaticamente."})
    if fields == {"queries"}:
        return schema.model_validate({"queries": [user.removeprefix("AFIRMAÇÃO:").strip()]})
    if {"verdict", "sources"} <= fields:
        cited = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)][:2]
        return schema.model_validate(
            {
                # O revisor falso discorda do checador falso: exercita o "mudou na revisão".
                "verdict": "falso" if "review" in model else "verdadeiro",
                "confidence": 0.9,
                "justification": "As fontes de teste confirmam a afirmação."
                if "review" not in model
                else "A revisão de teste contradiz a afirmação.",
                "sources": [
                    {"evidence": n, "stance": "apoia", "quote": "fonte de teste confirma"}
                    for n in cited
                ],
            }
        )
    return schema.model_validate({"ok": True})


class FakeSearchProvider:
    name = "fake"

    async def search(self, query: str, *, language: str | None, limit: int) -> list[Any]:
        from rtfc.search.base import SearchResult

        body = f"A fonte de teste confirma que {query} " + "Texto de apoio. " * 20
        return [
            SearchResult(
                url=f"https://{domain}/teste/{i}",
                title=f"Fonte de teste {i}",
                snippet=body[:120],
                provider=self.name,
                content=body,
            )
            for i, domain in enumerate(("aosfatos.org", "ibge.gov.br", "g1.globo.com"), 1)
        ][:limit]
