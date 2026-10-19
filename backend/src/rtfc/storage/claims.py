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
    model         TEXT,
    error         TEXT
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
    error: str | None = None

    def with_status(self, status: str, error: str | None = None) -> "StoredClaim":
        return replace(self, status=status, error=error)


class ClaimStore:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._db.executescript(SCHEMA)
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(claim)")}
        if "error" not in cols:  # bancos criados antes do M6
            with self._db:
                self._db.execute("ALTER TABLE claim ADD COLUMN error TEXT")

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

    def duplicates_of(self, claim_id: str) -> list[StoredClaim]:
        rows = self._db.execute(
            f"SELECT {', '.join(StoredClaim.__dataclass_fields__)} FROM claim WHERE dedup_of = ?",
            (claim_id,),
        ).fetchall()
        return [StoredClaim(*r) for r in rows]

    def interrupt_pending(self) -> int:
        """Checagens que estavam na fila quando o app fechou ficam como canceladas."""
        with self._db:
            cur = self._db.execute(
                "UPDATE claim SET status = 'cancelled' WHERE status IN ('queued', 'checking')"
            )
        return cur.rowcount

    def delete_session(self, session_id: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM claim WHERE session_id = ?", (session_id,))
