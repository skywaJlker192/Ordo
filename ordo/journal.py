"""Журнал операций в SQLite: на нём держатся история, статистика и откат."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL    NOT NULL,
    source TEXT    NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ops (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    kind     TEXT    NOT NULL,
    src      TEXT    NOT NULL,
    dst      TEXT    NOT NULL,
    rule     TEXT    NOT NULL,
    size     INTEGER NOT NULL DEFAULT 0
);
"""


class Journal:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def begin_batch(self, source: str) -> int:
        cur = self._db.execute(
            "INSERT INTO batches (ts, source) VALUES (?, ?)", (time.time(), source)
        )
        self._db.commit()
        return int(cur.lastrowid)

    def record(self, batch_id: int, kind: str, src: Path, dst: Path, rule: str, size: int) -> None:
        self._db.execute(
            "INSERT INTO ops (batch_id, kind, src, dst, rule, size) VALUES (?,?,?,?,?,?)",
            (batch_id, kind, str(src), str(dst), rule, size),
        )
        self._db.commit()

    def last_active_batch(self) -> Optional[int]:
        row = self._db.execute(
            "SELECT id FROM batches WHERE undone = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return int(row["id"]) if row else None

    def batch_exists(self, batch_id: int) -> Optional[sqlite3.Row]:
        return self._db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()

    def ops(self, batch_id: int) -> List[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM ops WHERE batch_id = ? ORDER BY id", (batch_id,)
        ).fetchall()

    def mark_undone(self, batch_id: int) -> None:
        self._db.execute("UPDATE batches SET undone = 1 WHERE id = ?", (batch_id,))
        self._db.commit()

    def history(self, limit: int = 10) -> List[sqlite3.Row]:
        return self._db.execute(
            """SELECT b.id, b.ts, b.source, b.undone, COUNT(o.id) AS n
               FROM batches b LEFT JOIN ops o ON o.batch_id = b.id
               GROUP BY b.id ORDER BY b.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def stats(self) -> dict:
        one = self._db.execute(
            """SELECT COUNT(o.id) AS ops, COALESCE(SUM(o.size), 0) AS bytes,
                      COUNT(DISTINCT o.batch_id) AS batches
               FROM ops o JOIN batches b ON b.id = o.batch_id WHERE b.undone = 0"""
        ).fetchone()
        undone = self._db.execute("SELECT COUNT(*) AS n FROM batches WHERE undone = 1").fetchone()
        rules = self._db.execute(
            """SELECT o.rule AS rule, COUNT(*) AS n
               FROM ops o JOIN batches b ON b.id = o.batch_id
               WHERE b.undone = 0 GROUP BY o.rule ORDER BY n DESC LIMIT 5"""
        ).fetchall()
        return {
            "ops": one["ops"],
            "bytes": one["bytes"],
            "batches": one["batches"],
            "undone": undone["n"],
            "top_rules": [(r["rule"], r["n"]) for r in rules],
        }
