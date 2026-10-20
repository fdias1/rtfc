"""Resultados das checagens: um por afirmação e por passada.

`live` é a checagem feita durante a sessão (modelo rápido); `review` é a rechecagem com o
modelo de qualidade depois da sessão (M6.1). Rechecar substitui o resultado da mesma passada.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

Pass = Literal["live", "review"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS check_run (
    claim_id        TEXT NOT NULL,
    pass            TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    confidence      REAL NOT NULL,
    justification   TEXT NOT NULL,
    model           TEXT,
    search_provider TEXT,
    queries         TEXT NOT NULL,
    checked_at      TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL,
    sources         TEXT NOT NULL,
    PRIMARY KEY (claim_id, pass)
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
        self._migrate_v1()

    def _migrate_v1(self) -> None:
        """Bancos anteriores ao M6.1 tinham `check_result` (um resultado por afirmação)."""
        exists = self._db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'check_result'"
        ).fetchone()
        if not exists:
            return
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO check_run SELECT claim_id, 'live', verdict, confidence,"
                " justification, model, search_provider, queries, checked_at, duration_ms,"
                " sources FROM check_result"
            )
            self._db.execute("DROP TABLE check_result")

    def save(self, c: StoredCheck, pass_: Pass = "live") -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO check_run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    c.claim_id, pass_, c.verdict, c.confidence, c.justification, c.model,
                    c.search_provider, json.dumps(list(c.queries), ensure_ascii=False),
                    c.checked_at, c.duration_ms,
                    json.dumps([s.__dict__ for s in c.sources], ensure_ascii=False),
                ),
            )  # fmt: skip

    def get(self, claim_id: str, pass_: Pass = "live") -> StoredCheck | None:
        row = self._db.execute(
            "SELECT claim_id, verdict, confidence, justification, model, search_provider,"
            " queries, checked_at, duration_ms, sources FROM check_run"
            " WHERE claim_id = ? AND pass = ?",
            (claim_id, pass_),
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
                "DELETE FROM check_run WHERE claim_id = ?", [(i,) for i in claim_ids]
            )
