"""Small, UI-independent clipboard history store for the Linux port."""

import sqlite3
import time
import re
import hashlib
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
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(entries)")}
        if "kind" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
        if "data" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN data BLOB")
        self.db.commit()

    def add(self, value: str):
        if not value or not value.strip():
            return
        self._add(value, "text", None)

    def add_image(self, data: bytes):
        if not data:
            return
        digest = hashlib.sha256(data).hexdigest()
        self._add("Image " + digest, "image", data)

    def _add(self, value, kind, data):
        with self.db:
            self.db.execute(
                "INSERT INTO entries(text, copied_at, kind, data) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(text) DO UPDATE SET copied_at=excluded.copied_at, "
                "kind=excluded.kind, data=excluded.data",
                (value, time.time(), kind, data),
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

    def list(self, query: str = "", mode: str = "exact", pins_position: str = "top"):
        rows = self.db.execute(
            "SELECT id, text, pinned, kind, data FROM entries "
            "ORDER BY copied_at DESC, id DESC"
        ).fetchall()
        if query:
            needle = query.casefold()
            def exact(row):
                return needle in row[1].casefold()
            def fuzzy(row):
                letters = iter(row[1].casefold())
                return all(any(char == found for found in letters) for char in needle)
            def regex(row):
                try:
                    return re.search(query, row[1], re.IGNORECASE) is not None
                except re.error:
                    return False
            tests = {"exact": exact, "fuzzy": fuzzy, "regex": regex}
            if mode == "mixed":
                for test in (exact, regex, fuzzy):
                    matching = [row for row in rows if test(row)]
                    if matching:
                        rows = matching
                        break
                else:
                    rows = []
            else:
                rows = [row for row in rows if tests.get(mode, exact)(row)]
        return sorted(rows, key=lambda row: row[2] if pins_position == "bottom" else -row[2])

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
