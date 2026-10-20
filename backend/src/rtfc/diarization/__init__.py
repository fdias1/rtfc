"""Diarização: quem está falando em cada segmento da transcrição (M4, ADR 0008)."""

from rtfc.diarization.clustering import (
    DEFAULT_THRESHOLD,
    MIN_EMBED_S,
    OnlineClusterer,
    recluster,
    remap,
    speaker_label,
)
from rtfc.diarization.service import DiarizationService, FakeEmbedder, SpeakerEmbedder

__all__ = [
    "DEFAULT_THRESHOLD",
    "MIN_EMBED_S",
    "DiarizationService",
    "FakeEmbedder",
    "OnlineClusterer",
    "SpeakerEmbedder",
    "recluster",
    "remap",
    "speaker_label",
]
