"""Resultados das checagens (um por afirmação, substituído ao rechecar)."""

import json
import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS check_result (
    claim_id        TEXT PRIMARY KEY,
    verdict         TEXT NOT NULL,
    confidence      REAL NOT NULL,
    justification   TEXT NOT NULL,
    model           TEXT,
    search_provider TEXT,
    queries         TEXT NOT NULL,
    checked_at      TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL,
    sources         TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredSource:
    url: str
    title: str
    domain: str
    tier: str
    stance: str
    quote: str
    published: str | None


@dataclass(frozen=True)
class StoredCheck:
    claim_id: str
    verdict: str
    confidence: float
    justification: str
    model: str | None
    search_provider: str | None
    queries: tuple[str, ...]
    checked_at: str
    duration_ms: int
    sources: tuple[StoredSource, ...]


class CheckStore:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._db.executescript(SCHEMA)

    def save(self, c: StoredCheck) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO check_result VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    c.claim_id, c.verdict, c.confidence, c.justification, c.model,
                    c.search_provider, json.dumps(list(c.queries), ensure_ascii=False),
                    c.checked_at, c.duration_ms,
                    json.dumps([s.__dict__ for s in c.sources], ensure_ascii=False),
                ),
            )  # fmt: skip

    def get(self, claim_id: str) -> StoredCheck | None:
        row = self._db.execute(
            "SELECT * FROM check_result WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if not row:
            return None
        (cid, verdict, conf, just, model, provider, queries, at, dur, sources) = row
        return StoredCheck(
            cid, verdict, conf, just, model, provider, tuple(json.loads(queries)), at, dur,
            tuple(StoredSource(**s) for s in json.loads(sources)),
        )  # fmt: skip

    def delete(self, claim_ids: list[str]) -> None:
        with self._db:
            self._db.executemany(
                "DELETE FROM check_result WHERE claim_id = ?", [(i,) for i in claim_ids]
            )
