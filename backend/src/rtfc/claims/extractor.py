"""Chamada ao LLM que extrai afirmações (e a que normaliza um trecho escolhido à mão)."""

from datetime import date
from importlib.resources import files

from pydantic import BaseModel, ConfigDict

from rtfc.llm import LlmClient, LlmResult
from rtfc.storage import StoredSegment

LANGUAGE_NAMES = {"pt": "português", "en": "inglês", "es": "espanhol"}


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_index: int
    source_text: str
    claim: str


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ExtractedClaim]
    last_sentence_incomplete: bool


class NormalizedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    verifiable: bool


def _prompt(name: str, language: str | None, when: date) -> str:
    template = files("rtfc.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")
    lang = LANGUAGE_NAMES.get(language or "", language or "o mesmo do discurso")
    return template.replace("{language}", lang).replace("{date}", when.isoformat())


def _lines(segments: list[StoredSegment]) -> str:
    return "\n".join(
        f"[{s.index}]{f' ({s.speaker})' if s.speaker else ''} {s.text}" for s in segments
    )


async def extract_claims(
    client: LlmClient,
    *,
    new: list[StoredSegment],
    context: list[StoredSegment],
    already: list[str],
    language: str | None,
    when: date,
) -> LlmResult[ExtractionResult]:
    user = (
        "CONTEXTO (não extraia daqui):\n"
        + (_lines(context) or "(nenhum)")
        + "\n\nNOVAS FRASES:\n"
        + _lines(new)
        + "\n\nAFIRMAÇÕES JÁ EXTRAÍDAS (não repita):\n"
        + ("\n".join(f"- {c}" for c in already[-30:]) or "(nenhuma)")
    )
    messages = [
        {"role": "system", "content": _prompt("extract_claims", language, when)},
        {"role": "user", "content": user},
    ]
    return await client.structured(messages, ExtractionResult)


async def normalize_excerpt(
    client: LlmClient,
    *,
    excerpt: str,
    context: list[StoredSegment],
    language: str | None,
    when: date,
) -> LlmResult[NormalizedClaim]:
    messages = [
        {"role": "system", "content": _prompt("normalize_claim", language, when)},
        {
            "role": "user",
            "content": "CONTEXTO:\n" + (_lines(context) or "(nenhum)") + f"\n\nTRECHO:\n{excerpt}",
        },
    ]
    return await client.structured(messages, NormalizedClaim)
