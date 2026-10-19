from pathlib import Path

from rtfc.storage import StoredSegment, StoredWord, SubtitleWriter, TranscriptStore, srt_time


def test_srt_time_format() -> None:
    assert srt_time(0) == "00:00:00,000"
    assert srt_time(3_723_456) == "01:02:03,456"


def test_subtitles_are_appended_incrementally(tmp_path: Path) -> None:
    w = SubtitleWriter(tmp_path)
    w.add(0, 1500, "Primeira frase.")
    # Lido antes de fechar: o arquivo já tem a legenda (gravação incremental).
    assert "Primeira frase." in w.srt_path.read_text(encoding="utf-8")
    w.add(2000, 3100, "Segunda.", speaker="Falante 1")
    w.close()
    assert w.srt_path.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,500\nPrimeira frase.\n\n"
        "2\n00:00:02,000 --> 00:00:03,100\nSegunda.\n\n"
    )
    vtt = w.vtt_path.read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:02.000 --> 00:00:03.100\n<v Falante 1>Segunda." in vtt


def test_transcript_store_roundtrip(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "db.sqlite")
    seg = StoredSegment(
        0,
        100,
        900,
        "Olá mundo.",
        (StoredWord(100, 400, "Olá", 0.9), StoredWord(400, 900, "mundo.", 0.8)),
    )
    store.add_segment("s1", seg)
    store.add_segment("s2", StoredSegment(0, 0, 10, "outra", ()))
    assert store.segments("s1") == [seg]
    assert len(store.segments("s2")) == 1
    store.close()
