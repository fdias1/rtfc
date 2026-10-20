"""Agrupamento de falantes por similaridade de cosseno entre embeddings (ADR 0008).

A unidade é o segmento da transcrição (uma frase): cada um vira um embedding e recebe o
falante do centróide mais parecido, ou um falante novo se nenhum passar do limiar.

- Ao vivo (`OnlineClusterer`): decide na hora, a cada segmento. Quando dois centróides
  ficam parecidos demais com o tempo, junta os dois e avisa quais rótulos mudaram.
- No fim (`recluster`): com todos os embeddings da sessão, refaz a atribuição algumas vezes
  (estilo k-means com fusão), o que corrige as decisões precoces do modo ao vivo.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float32]

DEFAULT_THRESHOLD = 0.6
MIN_EMBED_S = 0.8
"""Segmentos mais curtos que isso dão embeddings pouco confiáveis: não criam falante."""


def normalize(v: Vector) -> Vector:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def speaker_id(n: int) -> str:
    return f"S{n}"


def speaker_label(sid: str | None, names: dict[str, str] | None = None) -> str | None:
    """Nome para mostrar (e para os prompts): o dado pelo usuário ou "Falante N"."""
    if not sid:
        return None
    if names and names.get(sid):
        return names[sid]
    return f"Falante {sid[1:]}" if sid[:1] == "S" and sid[1:].isdigit() else sid


class OnlineClusterer:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold
        self._sums: dict[str, Vector] = {}
        self._next = 1
        self.last: str | None = None

    @property
    def speakers(self) -> list[str]:
        return list(self._sums)

    def _centroid(self, sid: str) -> Vector:
        return normalize(self._sums[sid])

    def _nearest(self, emb: Vector) -> tuple[str | None, float]:
        best, best_sim = None, -1.0
        for sid in self._sums:
            sim = float(self._centroid(sid) @ emb)
            if sim > best_sim:
                best, best_sim = sid, sim
        return best, best_sim

    def assign(
        self, emb: Vector | None, *, reliable: bool = True
    ) -> tuple[str | None, dict[str, str]]:
        """Devolve (falante do segmento, fusões {rótulo antigo: rótulo novo})."""
        if emb is None:
            return self.last, {}
        emb = normalize(emb)
        best, sim = self._nearest(emb)
        if not reliable:
            # Trecho curto: não cria falante nem mexe no centróide.
            sid = best if best is not None and sim >= self.threshold * 0.8 else self.last
            if sid is None and best is None:
                sid = self._new(emb)
            self.last = sid
            return sid, {}
        if best is not None and sim >= self.threshold:
            self._sums[best] = self._sums[best] + emb
            sid = best
        else:
            sid = self._new(emb)
        merges = self._merge_close()
        sid = merges.get(sid, sid)
        self.last = sid
        return sid, merges

    def _new(self, emb: Vector) -> str:
        sid = speaker_id(self._next)
        self._next += 1
        self._sums[sid] = emb.copy()
        return sid

    def _merge_close(self) -> dict[str, str]:
        merges: dict[str, str] = {}
        changed = True
        while changed:
            changed = False
            ids = list(self._sums)
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    if float(self._centroid(a) @ self._centroid(b)) >= self.threshold:
                        # O falante mais antigo (rótulo menor) fica com o nome.
                        self._sums[a] = self._sums[a] + self._sums.pop(b)
                        merges = {k: (a if v == b else v) for k, v in merges.items()}
                        merges[b] = a
                        changed = True
                        break
                if changed:
                    break
        return merges


def recluster(
    embeddings: Sequence[Vector | None],
    reliable: Sequence[bool],
    threshold: float = DEFAULT_THRESHOLD,
    iterations: int = 5,
) -> list[int | None]:
    """Atribui um grupo (0, 1, …) a cada segmento usando a sessão inteira.

    Começa pelo agrupamento ao vivo e então alterna: recalcula os centróides com os
    segmentos confiáveis, junta centróides parecidos, reatribui cada segmento ao mais
    próximo. Segmentos sem embedding herdam o grupo do anterior.
    """
    online = OnlineClusterer(threshold)
    labels: list[str | None] = [
        online.assign(e, reliable=r)[0] for e, r in zip(embeddings, reliable, strict=True)
    ]
    # Fusões do modo ao vivo reescrevem rótulos já dados; aplica no fim.
    alive = set(online.speakers)
    groups = [lab if lab in alive else None for lab in labels]

    vecs = [normalize(e) if e is not None else None for e in embeddings]
    for _ in range(iterations):
        cents: dict[str, Vector] = {}
        for g, v, r in zip(groups, vecs, reliable, strict=True):
            if g is not None and v is not None and r:
                cents[g] = cents.get(g, np.zeros_like(v)) + v
        if not cents:
            break
        cents = {k: normalize(c) for k, c in cents.items()}
        # Junta centróides parecidos.
        keys = sorted(cents, key=lambda k: int(k[1:]))
        alias: dict[str, str] = {}
        for i, a in enumerate(keys):
            if a in alias:
                continue
            for b in keys[i + 1 :]:
                if b not in alias and float(cents[a] @ cents[b]) >= threshold:
                    alias[b] = a
        cents = {k: c for k, c in cents.items() if k not in alias}
        new: list[str | None] = []
        for v in vecs:
            if v is None:
                new.append(None)
                continue
            new.append(max(cents, key=lambda k: float(cents[k] @ v)))
        if new == groups:
            break
        groups = new

    # Sem embedding: herda do anterior (ou do próximo, no começo).
    filled: list[str | None] = []
    for g in groups:
        filled.append(g if g is not None else (filled[-1] if filled else None))
    first = next((g for g in filled if g is not None), None)
    filled = [g if g is not None else first for g in filled]

    order: dict[str, int] = {}
    out: list[int | None] = []
    for g in filled:
        if g is None:
            out.append(None)
            continue
        out.append(order.setdefault(g, len(order)))
    return out


def remap(
    old: Sequence[str | None],
    new: Sequence[int | None],
    durations: Sequence[float],
) -> list[str | None]:
    """Traduz os grupos novos para rótulos, mantendo os antigos onde batem.

    Cada grupo novo fica com o rótulo antigo com que mais se sobrepõe (em duração), para
    que nomes dados pelo usuário sobrevivam ao refinamento. Os demais ganham rótulos novos.
    """
    overlap: dict[tuple[int, str], float] = {}
    for o, n, d in zip(old, new, durations, strict=True):
        if o is not None and n is not None:
            overlap[(n, o)] = overlap.get((n, o), 0.0) + d
    taken: set[str] = set()
    mapping: dict[int, str] = {}
    for (n, o), _ in sorted(overlap.items(), key=lambda kv: -kv[1]):
        if n in mapping or o in taken:
            continue
        mapping[n] = o
        taken.add(o)
    used = {int(o[1:]) for o in old if o is not None and o[1:].isdigit()} | {
        int(o[1:]) for o in taken
    }
    nxt = max(used, default=0) + 1
    for n in new:
        if n is not None and n not in mapping:
            mapping[n] = speaker_id(nxt)
            nxt += 1
    return [mapping[n] if n is not None else None for n in new]
