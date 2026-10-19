"""Prompt de veredicto, schema da resposta e regras de integridade (aplicadas por código)."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from rtfc.claims.extractor import LANGUAGE_NAMES, _prompt
from rtfc.llm import LlmClient, LlmResult
from rtfc.search.base import SearchResult

VerdictLabel = Literal["verdadeiro", "fora_de_contexto", "falso", "inconclusivo"]
Stance = Literal["apoia", "refuta", "contextualiza"]

MIN_SOURCES = 2
EVIDENCE_CHARS = 1600
QUOTE_MIN_SIMILARITY = 70


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[str]


class CitedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: int
    stance: Stance
    quote: str


class VerdictResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: VerdictLabel
    confidence: float
    justification: str
    sources: list[CitedSource]


@dataclass(frozen=True)
class ClaimBackground:
    """O que cerca a afirmação: sem isso, "o desemprego caiu" não diz de onde nem de quando."""

    claim_context: str | None = None
    content_context: str | None = None
    speaker: str | None = None
    transcript: str = ""

    def render(self) -> str:
        parts = []
        if self.content_context:
            parts.append(f"CONTEXTO DO CONTEÚDO: {self.content_context}")
        if self.speaker:
            parts.append(f"QUEM DISSE: {self.speaker}")
        if self.claim_context:
            parts.append(f"CONTEXTO DA AFIRMAÇÃO: {self.claim_context}")
        if self.transcript:
            parts.append(
                "TRANSCRIÇÃO AO REDOR (>> marca o trecho da afirmação):\n" + self.transcript[-4000:]
            )
        return "\n\n".join(parts)


@dataclass(frozen=True)
class Evidence:
    number: int
    result: SearchResult
    text: str
    """Trecho mais relevante da página (ou o snippet, se a página não pôde ser lida)."""


@dataclass(frozen=True)
class ValidSource:
    result: SearchResult
    stance: Stance
    quote: str


@dataclass(frozen=True)
class CheckedVerdict:
    verdict: VerdictLabel
    confidence: float
    justification: str
    sources: list[ValidSource]
    dropped: int
    """Citações descartadas pela validação (evidência inexistente ou repetida)."""


TIER_LABEL = {
    "primary": "fonte primária",
    "factchecker": "agência de checagem",
    "press": "imprensa",
}


def relevant_passage(content: str, claim: str, limit: int = EVIDENCE_CHARS) -> str:
    """Parágrafos mais parecidos com a afirmação, na ordem original, até `limit` caracteres."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", content) if len(p.strip()) > 40]
    if not paragraphs:
        return content[:limit]
    scored = sorted(
        range(len(paragraphs)),
        key=lambda i: fuzz.token_set_ratio(claim.lower(), paragraphs[i].lower()),
        reverse=True,
    )
    chosen: list[int] = []
    size = 0
    for i in scored:
        if size + len(paragraphs[i]) > limit and chosen:
            continue
        chosen.append(i)
        size += len(paragraphs[i])
        if size >= limit:
            break
    return "\n".join(paragraphs[i] for i in sorted(chosen))[:limit]


def format_evidence(items: list[Evidence]) -> str:
    blocks = []
    for e in items:
        r = e.result
        meta = [r.domain, TIER_LABEL.get(r.tier, "outro")]
        if r.published:
            meta.append(f"publicado: {r.published[:10]}")
        blocks.append(f"[{e.number}] {r.title}\n({'; '.join(meta)})\n{e.text}")
    return "\n\n".join(blocks)


async def plan_queries(
    client: LlmClient,
    claim: str,
    *,
    language: str | None,
    when: date,
    background: ClaimBackground | None = None,
) -> LlmResult[SearchPlan]:
    extra = background.render() if background else ""
    messages = [
        {"role": "system", "content": _prompt("search_queries", language, when)},
        {"role": "user", "content": f"AFIRMAÇÃO: {claim}" + (f"\n\n{extra}" if extra else "")},
    ]
    return await client.structured(messages, SearchPlan)


async def judge(
    client: LlmClient,
    claim: str,
    evidence: list[Evidence],
    *,
    language: str | None,
    when: date,
    background: ClaimBackground | None = None,
) -> LlmResult[VerdictResult]:
    extra = background.render() if background else ""
    messages = [
        {"role": "system", "content": _prompt("verdict", language, when)},
        {
            "role": "user",
            "content": f"AFIRMAÇÃO: {claim}"
            + (f"\n\n{extra}" if extra else "")
            + f"\n\nEVIDÊNCIAS:\n\n{format_evidence(evidence)}",
        },
    ]
    return await client.structured(messages, VerdictResult)


def validate(raw: VerdictResult, evidence: list[Evidence], language: str | None) -> CheckedVerdict:
    """Regras de integridade (PRD RF5.4), independentes do que o modelo disse.

    - Só valem citações de evidências que existem (o modelo não tem como inventar URL:
      ele cita números, que viram as URLs que nós mesmos buscamos).
    - Cada evidência conta uma vez; trechos que não aparecem na evidência são apagados.
    - Com menos de 2 fontes válidas, o veredicto vira "inconclusivo".
    """
    by_number = {e.number: e for e in evidence}
    seen: set[int] = set()
    valid: list[ValidSource] = []
    dropped = 0
    for s in raw.sources:
        e = by_number.get(s.evidence)
        if e is None or s.evidence in seen:
            dropped += 1
            continue
        seen.add(s.evidence)
        quote = s.quote.strip().strip("\"'“”«»").strip()
        if quote and fuzz.partial_ratio(quote.lower(), e.text.lower()) < QUOTE_MIN_SIMILARITY:
            quote = ""
        valid.append(ValidSource(e.result, s.stance, quote))

    verdict: VerdictLabel = raw.verdict
    confidence = min(1.0, max(0.0, raw.confidence))
    justification = raw.justification.strip()
    if len(valid) < MIN_SOURCES and verdict != "inconclusivo":
        verdict = "inconclusivo"
        confidence = min(confidence, 0.3)
        note = (
            "Evidência insuficiente: menos de duas fontes válidas."
            if LANGUAGE_NAMES.get(language or "pt") == "português"
            else "Insufficient evidence: fewer than two valid sources."
        )
        justification = f"{note} {justification}".strip()
    return CheckedVerdict(verdict, confidence, justification, valid, dropped)
