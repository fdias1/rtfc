"""Afirmações persistidas no mesmo SQLite da transcrição."""

import sqlite3
from dataclasses import asdict, dataclass, replace

SCHEMA = """
CREATE TABLE IF NOT EXISTS claim (
    id            TEXT PRIMARY KEY,
    session_id    TEXT    NOT NULL,
    origin        TEXT    NOT NULL,
    text          TEXT    NOT NULL,
    source_text   TEXT    NOT NULL,
    from_segment  INTEGER NOT NULL,
    from_word     INTEGER NOT NULL,
    to_segment    INTEGER NOT NULL,
    to_word       INTEGER NOT NULL,
    start_ms      INTEGER NOT NULL,
    end_ms        INTEGER NOT NULL,
    status        TEXT    NOT NULL,
    dedup_of      TEXT,
    speaker       TEXT,
    created_at    TEXT    NOT NULL,
    model         TEXT
);
CREATE INDEX IF NOT EXISTS claim_session ON claim(session_id, start_ms);
"""


@dataclass(frozen=True)
class StoredClaim:
    id: str
    session_id: str
    origin: str
    text: str
    source_text: str
    from_segment: int
    from_word: int
    to_segment: int
    to_word: int
    start_ms: int
    end_ms: int
    status: str
    dedup_of: str | None
    speaker: str | None
    created_at: str
    model: str | None

    def with_status(self, status: str) -> "StoredClaim":
        return replace(self, status=status)


class ClaimStore:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._db.executescript(SCHEMA)

    def upsert(self, claim: StoredClaim) -> None:
        data = asdict(claim)
        cols = ", ".join(data)
        marks = ", ".join(f":{k}" for k in data)
        with self._db:
            self._db.execute(f"INSERT OR REPLACE INTO claim ({cols}) VALUES ({marks})", data)

    def get(self, claim_id: str) -> StoredClaim | None:
        row = self._db.execute(
            f"SELECT {', '.join(StoredClaim.__dataclass_fields__)} FROM claim WHERE id = ?",
            (claim_id,),
        ).fetchone()
        return StoredClaim(*row) if row else None

    def for_session(self, session_id: str) -> list[StoredClaim]:
        rows = self._db.execute(
            f"SELECT {', '.join(StoredClaim.__dataclass_fields__)} FROM claim"
            " WHERE session_id = ? ORDER BY start_ms, created_at",
            (session_id,),
        ).fetchall()
        return [StoredClaim(*r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM claim WHERE session_id = ?", (session_id,))
