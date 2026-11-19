"""Small, UI-independent clipboard history store for the Linux port."""

import sqlite3
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote
from search import match

PIN_KEYS = "bcdefghijklmnorstuxy"


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
        if "first_copied_at" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN first_copied_at REAL")
        if "copy_count" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN copy_count INTEGER")
        if "pin_order" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN pin_order INTEGER")
        if "pin_key" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN pin_key TEXT")
        self.db.execute("UPDATE entries SET first_copied_at=copied_at WHERE first_copied_at IS NULL")
        self.db.execute("UPDATE entries SET copy_count=1 WHERE copy_count IS NULL")
        self.db.execute("UPDATE entries SET pin_order=id WHERE pinned=1 AND pin_order IS NULL")
        assigned = {row[0] for row in self.db.execute(
            "SELECT pin_key FROM entries WHERE pinned=1 AND pin_key IS NOT NULL"
        )}
        for entry_id, in self.db.execute(
            "SELECT id FROM entries WHERE pinned=1 AND pin_key IS NULL ORDER BY pin_order, id"
        ).fetchall():
            key = next((key for key in PIN_KEYS if key not in assigned), None)
            if key:
                self.db.execute("UPDATE entries SET pin_key=? WHERE id=?", (key, entry_id))
                assigned.add(key)
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

    def add_rich(self, text: str, html: bytes):
        if text and html:
            self._add(text, "rich", html)

    def add_files(self, uris):
        uris = [uri for uri in uris if uri.startswith("file://")]
        if not uris:
            return
        data = ("\r\n".join(uris) + "\r\n").encode("utf-8")
        names = [Path(unquote(urlparse(uri).path)).name for uri in uris]
        title = "Files: " + ", ".join(names[:3])
        if len(names) > 3:
            title += f" (+{len(names) - 3})"
        self._add(title + " " + hashlib.sha256(data).hexdigest(), "files", data)

    def _add(self, value, kind, data):
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT INTO entries(text, copied_at, first_copied_at, copy_count, kind, data) "
                "VALUES (?, ?, ?, 1, ?, ?) "
                "ON CONFLICT(text) DO UPDATE SET copied_at=excluded.copied_at, "
                "copy_count=entries.copy_count+1, "
                "kind=CASE WHEN excluded.kind='text' AND entries.kind!='text' "
                "THEN entries.kind ELSE excluded.kind END, "
                "data=CASE WHEN excluded.kind='text' AND entries.kind!='text' "
                "THEN entries.data ELSE excluded.data END",
                (value, now, now, kind, data),
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

    def list(self, query: str = "", mode: str = "exact", pins_position: str = "top",
             sort_by: str = "last_copied"):
        rows = self.db.execute(
            "SELECT id, text, pinned, kind, data, first_copied_at, copy_count, "
            "pin_order, copied_at, pin_key FROM entries "
            "ORDER BY copied_at DESC, id DESC"
        ).fetchall()
        candidates = ("exact", "regex", "fuzzy") if mode == "mixed" else (mode,)
        matches = []
        effective_mode = candidates[-1]
        for candidate in candidates:
            matches = [(row, result) for row in rows
                       if (result := match(row[1], query, candidate)) is not None]
            effective_mode = candidate
            if matches or mode != "mixed":
                break
        metric = {"first_copied": 5, "most_copied": 6}.get(sort_by, 8)
        def order(item):
            row, result = item
            if row[2]:
                return (1 if pins_position == "bottom" else 0, row[7] or row[0], 0, 0)
            score = result[0] if query and effective_mode == "fuzzy" else 0
            return (0 if pins_position == "bottom" else 1, score, -row[metric], -row[0])
        return [row[:5] + (row[9], result[1]) for row, result in sorted(matches, key=order)]

    def pin(self, entry_id: int, pinned: bool):
        with self.db:
            next_order = self.db.execute(
                "SELECT COALESCE(MAX(pin_order), 0) + 1 FROM entries"
            ).fetchone()[0]
            assigned = {row[0] for row in self.db.execute(
                "SELECT pin_key FROM entries WHERE pinned=1 AND id<>? AND pin_key IS NOT NULL",
                (entry_id,)
            )}
            key = next((key for key in PIN_KEYS if key not in assigned), None) if pinned else None
            self.db.execute("UPDATE entries SET pinned=?, pin_order=?, pin_key=? WHERE id=?",
                            (int(pinned), next_order if pinned else None, key, entry_id))

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
