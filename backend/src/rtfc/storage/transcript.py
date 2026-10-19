"""Transcrição persistida em SQLite: a fonte da verdade (SRT/VTT são derivados)."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS segment (
    id          INTEGER PRIMARY KEY,
    session_id  TEXT    NOT NULL,
    idx         INTEGER NOT NULL,
    speaker     TEXT,
    start_ms    INTEGER NOT NULL,
    end_ms      INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    UNIQUE (session_id, idx)
);
CREATE TABLE IF NOT EXISTS word (
    segment_id  INTEGER NOT NULL REFERENCES segment(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    start_ms    INTEGER NOT NULL,
    end_ms      INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    prob        REAL    NOT NULL,
    PRIMARY KEY (segment_id, idx)
);
CREATE INDEX IF NOT EXISTS segment_session ON segment(session_id, start_ms);
"""


@dataclass(frozen=True)
class StoredWord:
    start_ms: int
    end_ms: int
    text: str
    prob: float


@dataclass(frozen=True)
class StoredSegment:
    index: int
    start_ms: int
    end_ms: int
    text: str
    words: tuple[StoredWord, ...]
    speaker: str | None = None


class TranscriptStore:
    """Usado só pela thread do event loop (chamadas curtas, sem I/O de rede)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    def add_segment(self, session_id: str, seg: StoredSegment) -> None:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO segment (session_id, idx, speaker, start_ms, end_ms, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, seg.index, seg.speaker, seg.start_ms, seg.end_ms, seg.text),
            )
            self._db.executemany(
                "INSERT INTO word (segment_id, idx, start_ms, end_ms, text, prob)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (cur.lastrowid, i, w.start_ms, w.end_ms, w.text, w.prob)
                    for i, w in enumerate(seg.words)
                ],
            )

    def segments(self, session_id: str) -> list[StoredSegment]:
        rows = self._db.execute(
            "SELECT id, idx, speaker, start_ms, end_ms, text FROM segment"
            " WHERE session_id = ? ORDER BY idx",
            (session_id,),
        ).fetchall()
        out = []
        for seg_id, idx, speaker, start, end, text in rows:
            words = tuple(
                StoredWord(*w)
                for w in self._db.execute(
                    "SELECT start_ms, end_ms, text, prob FROM word"
                    " WHERE segment_id = ? ORDER BY idx",
                    (seg_id,),
                )
            )
            out.append(StoredSegment(idx, start, end, text, words, speaker))
        return out

    def close(self) -> None:
        self._db.close()
