"""Diarização (M4): agrupamento, refinamento, rótulos, renomear e legendas."""

import asyncio
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rtfc.config import MemorySecretStore, SettingsStore
from rtfc.diarization import DiarizationService, OnlineClusterer, recluster, remap, speaker_label
from rtfc.diarization.session import SessionDiarizer
from rtfc.protocol import SpeakersUpdated
from rtfc.sessions import Session, SessionManager
from rtfc.storage import StoredSegment, TranscriptStore
from rtfc.stt.base import Word
from rtfc.stt.segmenter import Segment

RATE = 16_000


def v(*xs: float) -> np.ndarray:
    return np.array(xs, dtype=np.float32)


A, B = v(1, 0, 0), v(0, 1, 0)


def test_online_clusterer_separates_and_groups() -> None:
    c = OnlineClusterer(0.6)
    assert c.assign(A)[0] == "S1"
    assert c.assign(B)[0] == "S2"
    assert c.assign(v(0.9, 0.1, 0))[0] == "S1"
    assert c.assign(v(0.1, 0.95, 0))[0] == "S2"


def test_short_segment_does_not_create_a_speaker() -> None:
    c = OnlineClusterer(0.6)
    c.assign(A)
    sid, _ = c.assign(B, reliable=False)
    assert sid == "S1"  # herda o último em vez de inventar um falante
    assert c.speakers == ["S1"]


def test_online_merges_speakers_that_converge() -> None:
    c = OnlineClusterer(0.6)
    c.assign(v(1, 0, 0))
    assert c.assign(v(0.5, 0.86, 0))[0] == "S2"  # cos 0.5: falante novo
    # Mais fala no meio do caminho aproxima os dois centróides até juntar.
    merged: dict[str, str] = {}
    for _ in range(3):
        _, m = c.assign(v(0.8, 0.6, 0))
        merged.update(m)
    assert merged == {"S2": "S1"}
    assert c.speakers == ["S1"]


def test_recluster_fixes_early_online_mistakes() -> None:
    # O segundo trecho passa do limiar com A (cos 0,62) antes de B existir: ao vivo vira A.
    # Com a sessão toda, fica com B, que é mais parecido (cos 0,78).
    embs = [A, v(0.62, 0.78, 0), B, A, B, B, A]
    groups = recluster(embs, [True] * len(embs), 0.6)
    assert groups == [0, 1, 1, 0, 1, 1, 0]


def test_recluster_without_embeddings_inherits_previous() -> None:
    groups = recluster([A, None, B, None], [True, False, True, False], 0.6)
    assert groups == [0, 0, 1, 1]


def test_remap_keeps_existing_labels_and_names() -> None:
    old = ["S1", "S1", "S2", "S2", "S1"]
    new = [1, 1, 0, 0, 2]
    assert remap(old, new, [1.0] * 5) == ["S1", "S1", "S2", "S2", "S3"]


def test_speaker_label() -> None:
    assert speaker_label("S2") == "Falante 2"
    assert speaker_label("S2", {"S2": "Ana"}) == "Ana"
    assert speaker_label(None) is None


# --- Integração com as sessões ---------------------------------------------------

TONES = (220.0, 660.0)


class ToneEmbedder:
    """Embedding = qual dos dois tons domina o trecho (dois "falantes" bem distintos)."""

    def embed(self, audio: np.ndarray) -> np.ndarray | None:
        if len(audio) < RATE // 4:
            return None
        t = np.arange(len(audio)) / RATE
        power = [abs(np.dot(audio, np.exp(-2j * np.pi * f * t))) for f in TONES]
        out = np.zeros(3, dtype=np.float32)
        out[int(np.argmax(power))] = 1.0
        return out


def tone_audio(plan: list[int], seconds: float = 1.5) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return np.concatenate([0.3 * np.sin(2 * np.pi * TONES[k] * t) for k in plan]).astype(np.float32)


def segment(i: int, seconds: float = 1.5) -> Segment:
    start = i * seconds
    return Segment((Word(f" frase{i}.", start, start + seconds - 0.1),))


@pytest.fixture
def manager(tmp_path: Path) -> SessionManager:
    store = TranscriptStore(tmp_path / "db.sqlite")
    secrets = MemorySecretStore()
    settings = SettingsStore(tmp_path / "settings.json", secrets)
    return SessionManager(
        tmp_path / "sessions",
        store=store,
        settings=settings,
        secrets=secrets,
        diarization=DiarizationService(ToneEmbedder),  # type: ignore[arg-type]
    )


async def test_session_assigns_speakers_and_writes_vtt_voices(manager: SessionManager) -> None:
    events: list[Any] = []

    async def emit(ev: Any) -> None:
        events.append(ev)

    info = manager._new_info("file", "pt")
    session = Session(info, emit, manager.store)
    plan = [0, 1, 0, 1]
    pcm = (tone_audio(plan) * 32767).astype("<i2").tobytes()
    session.file_pcm = bytearray(pcm)
    assert manager.diarization is not None
    session.diarizer = SessionDiarizer(manager.diarization, 0.6)
    for i in range(len(plan)):
        await session.on_segment(segment(i), 0.0)
    session.subtitles.close()
    assert manager.store is not None
    assert [s.speaker for s in manager.store.segments(info.id)] == ["S1", "S2", "S1", "S2"]
    vtt = (Path(info.dir) / "transcricao.vtt").read_text()
    assert "<v Falante 1> frase0." not in vtt  # o texto vem sem o espaço inicial
    assert "<v Falante 1>frase0." in vtt and "<v Falante 2>frase1." in vtt


async def test_refine_and_rename_speakers_of_a_saved_session(
    manager: SessionManager, tmp_path: Path
) -> None:
    plan = [0, 0, 1, 0, 1, 1]
    wav = tmp_path / "debate.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((tone_audio(plan) * 32767).astype("<i2").tobytes())
    info = manager._new_info("file", "pt", status="completed", audio_path=str(wav))
    Session.write_info(info)
    assert manager.store is not None
    for i in range(len(plan)):
        # Tudo atribuído a um falante só (diarização desligada na época, por exemplo).
        manager.store.add_segment(
            info.id, StoredSegment(i, int(i * 1500), int(i * 1500 + 1400), f"frase{i}.", (), "S1")
        )
    events: list[Any] = []

    async def listener(ev: Any) -> None:
        events.append(ev)

    manager.add_listener(listener)
    result = await manager.refine_speakers(info.id, request_id="r1")
    assert isinstance(result, SpeakersUpdated)
    speakers = [s.speaker for s in manager.store.segments(info.id)]
    assert speakers == ["S1", "S1", "S2", "S1", "S2", "S2"]
    assert {a.index for a in result.segments} == {2, 4, 5}

    renamed = await manager.rename_speaker(info.id, "S2", "  Ana  ")
    assert renamed.speakers == {"S2": "Ana"}
    vtt = (Path(info.dir) / "transcricao.vtt").read_text()
    assert "<v Falante 1>frase0." in vtt and "<v Ana>frase2." in vtt
    assert vtt.count("-->") == len(plan)

    cleared = await manager.rename_speaker(info.id, "S2", "")
    assert cleared.speakers == {}


async def test_live_does_not_wait_for_the_model_to_load() -> None:
    service = DiarizationService(ToneEmbedder)  # type: ignore[arg-type]
    live = SessionDiarizer(service, 0.6, wait_model=False)
    sid, _ = await live.assign(0, tone_audio([0]))
    assert sid is None  # modelo ainda carregando: sem falante, sem esperar
    await asyncio.sleep(0.05)
    assert service.loaded
    assert (await live.assign(1, tone_audio([1])))[0] == "S1"
    assert live.refine() == {0: "S1"}  # o fim da sessão preenche pelo vizinho
