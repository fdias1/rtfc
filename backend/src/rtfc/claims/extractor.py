"""Chamada ao LLM que extrai afirmações (e a que normaliza um trecho escolhido à mão)."""

from datetime import date
from importlib.resources import files

from pydantic import BaseModel, ConfigDict

from rtfc.diarization.clustering import speaker_label
from rtfc.llm import LlmClient, LlmResult
from rtfc.storage import StoredSegment

LANGUAGE_NAMES = {"pt": "português", "en": "inglês", "es": "espanhol"}


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_index: int
    source_text: str
    claim: str
    context: str
    score: int


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ExtractedClaim]
    last_sentence_incomplete: bool


class ContentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: str


class NormalizedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    verifiable: bool


def _prompt(name: str, language: str | None, when: date) -> str:
    template = files("rtfc.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")
    lang = LANGUAGE_NAMES.get(language or "", language or "o mesmo do discurso")
    return template.replace("{language}", lang).replace("{date}", when.isoformat())


def _lines(segments: list[StoredSegment], speakers: dict[str, str] | None = None) -> str:
    def line(s: StoredSegment) -> str:
        who = speaker_label(s.speaker, speakers)
        return f"[{s.index}]{f' ({who})' if who else ''} {s.text}"

    return "\n".join(line(s) for s in segments)


async def extract_claims(
    client: LlmClient,
    *,
    new: list[StoredSegment],
    context: list[StoredSegment],
    already: list[str],
    language: str | None,
    when: date,
    content_context: str | None = None,
    speakers: dict[str, str] | None = None,
) -> LlmResult[ExtractionResult]:
    user = (
        "CONTEXTO DO CONTEÚDO:\n"
        + (content_context or "(ainda não definido)")
        + "\n\nFRASES ANTERIORES (não extraia daqui):\n"
        + (_lines(context, speakers) or "(nenhuma)")
        + "\n\nNOVAS FRASES:\n"
        + _lines(new, speakers)
        + "\n\nAFIRMAÇÕES JÁ EXTRAÍDAS (não repita):\n"
        + ("\n".join(f"- {c}" for c in already[-30:]) or "(nenhuma)")
    )
    messages = [
        {"role": "system", "content": _prompt("extract_claims", language, when)},
        {"role": "user", "content": user},
    ]
    return await client.structured(messages, ExtractionResult)


async def generate_context(
    client: LlmClient,
    *,
    segments: list[StoredSegment],
    language: str | None,
    when: date,
    hint: str | None = None,
    speakers: dict[str, str] | None = None,
) -> LlmResult[ContentContext]:
    # Começo + trecho mais recente: o começo costuma apresentar quem fala e o tema.
    picked = segments if len(segments) <= 60 else segments[:30] + segments[-30:]
    user = "TRANSCRIÇÃO:\n" + _lines(picked, speakers)
    if hint:
        user = f"CONTEXTO ANTERIOR (atualize se necessário):\n{hint}\n\n{user}"
    messages = [
        {"role": "system", "content": _prompt("content_context", language, when)},
        {"role": "user", "content": user},
    ]
    return await client.structured(messages, ContentContext)


async def normalize_excerpt(
    client: LlmClient,
    *,
    excerpt: str,
    context: list[StoredSegment],
    language: str | None,
    when: date,
    content_context: str | None = None,
    speakers: dict[str, str] | None = None,
) -> LlmResult[NormalizedClaim]:
    messages = [
        {"role": "system", "content": _prompt("normalize_claim", language, when)},
        {
            "role": "user",
            "content": "CONTEXTO DO CONTEÚDO:\n"
            + (content_context or "(não definido)")
            + "\n\nTRANSCRIÇÃO AO REDOR:\n"
            + (_lines(context, speakers) or "(nenhuma)")
            + f"\n\nTRECHO:\n{excerpt}",
        },
    ]
    return await client.structured(messages, NormalizedClaim)
