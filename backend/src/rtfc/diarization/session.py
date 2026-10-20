"""Estado da diarização de uma sessão: embeddings por segmento e rótulos atribuídos."""

import logging

from rtfc.diarization.clustering import MIN_EMBED_S, OnlineClusterer, Vector, recluster, remap
from rtfc.diarization.service import DiarizationService

log = logging.getLogger(__name__)

Changes = dict[int, str | None]
"""{índice do segmento: novo falante}."""


class SessionDiarizer:
    def __init__(
        self, service: DiarizationService, threshold: float, *, wait_model: bool = True
    ) -> None:
        self._service = service
        self._wait_model = wait_model
        """Arquivo: espera o modelo carregar. Ao vivo: não segura a transcrição."""
        self.threshold = threshold
        self._online = OnlineClusterer(threshold)
        self.embeddings: dict[int, Vector | None] = {}
        self.reliable: dict[int, bool] = {}
        self.durations: dict[int, float] = {}
        self.labels: dict[int, str | None] = {}

    async def assign(self, index: int, audio: Vector | None) -> tuple[str | None, Changes]:
        """Falante do segmento novo e as mudanças em segmentos anteriores (fusões)."""
        duration = len(audio) / 16_000 if audio is not None else 0.0
        emb = None
        if not self._wait_model and not self._service.loaded:
            # Ao vivo, a primeira vez (download do modelo) não pode segurar a transcrição:
            # o segmento fica sem embedding e o refinamento do fim atribui pelo vizinho.
            self._service.warm_up()
        elif audio is not None and len(audio):
            try:
                emb = await self._service.embed(audio)
            except Exception:
                log.exception("embedding de falante falhou")
        reliable = emb is not None and duration >= MIN_EMBED_S
        sid, merges = self._online.assign(emb, reliable=reliable)
        changes: Changes = {}
        for i, label in self.labels.items():
            if label in merges:
                changes[i] = merges[label]
        self.labels.update(changes)
        self.embeddings[index] = emb
        self.reliable[index] = reliable
        self.durations[index] = duration
        self.labels[index] = sid
        return sid, changes

    def refine(self) -> Changes:
        """Refaz os grupos com a sessão inteira (fim da sessão). Mantém os rótulos onde batem."""
        order = sorted(self.labels)
        if not order:
            return {}
        groups = recluster(
            [self.embeddings[i] for i in order], [self.reliable[i] for i in order], self.threshold
        )
        mapped = remap([self.labels[i] for i in order], groups, [self.durations[i] for i in order])
        changes = {i: m for i, m in zip(order, mapped, strict=True) if m != self.labels[i]}
        self.labels.update(changes)
        return changes
