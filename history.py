"""Small, UI-independent clipboard history store for the Linux port."""

import sqlite3
import time
from pathlib import Path


class History:
    def __init__(self, path: Path, limit: int = 200):
        self.limit = limit
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, "
            "copied_at REAL NOT NULL, pinned INTEGER NOT NULL DEFAULT 0)"
        )
        self.db.commit()

    def add(self, value: str):
        if not value or not value.strip():
            return
        with self.db:
            self.db.execute(
                "INSERT INTO entries(text, copied_at) VALUES (?, ?) "
                "ON CONFLICT(text) DO UPDATE SET copied_at=excluded.copied_at",
                (value, time.time()),
            )
            self._prune()

    def _prune(self):
        self.db.execute(
            "DELETE FROM entries WHERE id IN ("
            "SELECT id FROM entries WHERE pinned=0 ORDER BY copied_at DESC, id DESC "
            "LIMIT -1 OFFSET ?)",
            (self.limit,),
        )

    def set_limit(self, limit: int):
        self.limit = limit
        with self.db:
            self._prune()

    def list(self, query: str = ""):
        # Filtering in Python keeps search case insensitive for Unicode text.
        rows = self.db.execute(
            "SELECT id, text, pinned FROM entries "
            "ORDER BY pinned DESC, copied_at DESC, id DESC"
        ).fetchall()
        needle = query.casefold()
        return [row for row in rows if needle in row[1].casefold()]

    def pin(self, entry_id: int, pinned: bool):
        with self.db:
            self.db.execute("UPDATE entries SET pinned=? WHERE id=?", (int(pinned), entry_id))

    def delete(self, entry_id: int):
        with self.db:
            self.db.execute("DELETE FROM entries WHERE id=?", (entry_id,))

    def clear(self):
        with self.db:
            self.db.execute("DELETE FROM entries WHERE pinned=0")

    def clear_all(self):
        with self.db:
            self.db.execute("DELETE FROM entries")

    def close(self):
        self.db.close()
