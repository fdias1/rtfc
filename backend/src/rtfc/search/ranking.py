"""Classifica os resultados por tipo de fonte e escolhe as melhores evidências."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from rtfc.search.base import SearchResult, Tier
from rtfc.search.data import BLOCKED, TIERS

TIER_WEIGHT: dict[Tier, int] = {"primary": 3, "factchecker": 2, "press": 1, "other": 0}
MAX_PER_DOMAIN = 2
TIER_CAP: dict[Tier, int] = {"primary": 10, "factchecker": 3, "press": 3, "other": 3}
"""Cota por tipo entre os candidatos: imprensa e "outros" entram, mas não dominam (ADR 0006)."""


@dataclass(frozen=True)
class DomainLists:
    primary: tuple[str, ...]
    factchecker: tuple[str, ...]
    press: tuple[str, ...]
    blocked: tuple[str, ...]

    @classmethod
    def for_language(
        cls, language: str | None, extra_blocked: tuple[str, ...] = ()
    ) -> "DomainLists":
        lists = TIERS.get(language or "pt", TIERS["pt"])
        return cls(lists["primary"], lists["factchecker"], lists["press"], BLOCKED + extra_blocked)


def _matches(url: str, pattern: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    domain, _, path = pattern.partition("/")
    if domain.startswith("."):
        host_ok = host.endswith(domain)
    else:
        host_ok = host == domain or host.endswith("." + domain)
    return host_ok and (not path or parts.path.lstrip("/").startswith(path))


def classify(url: str, lists: DomainLists) -> Tier | None:
    """Tipo da fonte, ou None se o domínio está bloqueado."""
    if any(_matches(url, p) for p in lists.blocked):
        return None
    # Checadores antes de imprensa: "g1.globo.com/fato-ou-fake" também casa "g1.globo.com".
    for tier in ("primary", "factchecker", "press"):
        if any(_matches(url, p) for p in getattr(lists, tier)):
            return tier
    return "other"


def _canonical(url: str) -> str:
    p = urlsplit(url)
    return f"{(p.hostname or '').removeprefix('www.')}{p.path.rstrip('/')}"


def rank(results: list[SearchResult], lists: DomainLists, limit: int) -> list[SearchResult]:
    """Junta os resultados das consultas, remove bloqueados e repetidos e ordena.

    Ordem: tipo da fonte (primárias > checadores > imprensa > outros), depois quantas
    consultas acharam a página, depois a posição original. No máximo 2 por domínio e
    uma cota por tipo, para a imprensa não ocupar todas as vagas.
    """
    merged: dict[str, tuple[SearchResult, int]] = {}
    for pos, r in enumerate(results):
        tier = classify(r.url, lists)
        if tier is None:
            continue
        key = _canonical(r.url)
        if key in merged:
            prev, first_pos = merged[key]
            merged[key] = (prev.with_(queries=prev.queries + r.queries), first_pos)
        else:
            merged[key] = (r.with_(tier=tier), pos)
    ordered = sorted(
        merged.values(), key=lambda x: (-TIER_WEIGHT[x[0].tier], -len(x[0].queries), x[1])
    )
    out: list[SearchResult] = []
    per_domain: dict[str, int] = {}
    per_tier: dict[str, int] = {}
    for r, _ in ordered:
        if per_domain.get(r.domain, 0) >= MAX_PER_DOMAIN:
            continue
        if per_tier.get(r.tier, 0) >= TIER_CAP[r.tier]:
            continue
        per_domain[r.domain] = per_domain.get(r.domain, 0) + 1
        per_tier[r.tier] = per_tier.get(r.tier, 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    return out
