"""Small, UI-independent clipboard history store for the Linux port."""

import sqlite3
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote
from search import match

PIN_KEYS = "bcdefghijklmnorstuxy"
_UNSET = object()


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
        if "alias" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN alias TEXT")
        if "source_app" not in columns:
            self.db.execute("ALTER TABLE entries ADD COLUMN source_app TEXT")
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

    def add(self, value: str, source_app=None):
        if not value or not value.strip():
            return
        self._add(value, "text", None, source_app)

    def add_image(self, data: bytes, source_app=None):
        if not data:
            return
        digest = hashlib.sha256(data).hexdigest()
        self._add("Image " + digest, "image", data, source_app)

    def add_rich(self, text: str, html: bytes, source_app=None):
        if text and html:
            self._add(text, "rich", html, source_app)

    def add_files(self, uris, source_app=None):
        uris = [uri for uri in uris if uri.startswith("file://")]
        if not uris:
            return
        data = ("\r\n".join(uris) + "\r\n").encode("utf-8")
        names = [Path(unquote(urlparse(uri).path)).name for uri in uris]
        title = "Files: " + ", ".join(names[:3])
        if len(names) > 3:
            title += f" (+{len(names) - 3})"
        self._add(title + " " + hashlib.sha256(data).hexdigest(), "files", data, source_app)

    def _add(self, value, kind, data, source_app):
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT INTO entries(text, copied_at, first_copied_at, copy_count, kind, data, source_app) "
                "VALUES (?, ?, ?, 1, ?, ?, ?) "
                "ON CONFLICT(text) DO UPDATE SET copied_at=excluded.copied_at, "
                "copy_count=entries.copy_count+1, "
                "kind=CASE WHEN excluded.kind='text' AND entries.kind!='text' "
                "THEN entries.kind ELSE excluded.kind END, "
                "data=CASE WHEN excluded.kind='text' AND entries.kind!='text' "
                "THEN entries.data ELSE excluded.data END, "
                "source_app=COALESCE(excluded.source_app, entries.source_app)",
                (value, now, now, kind, data, source_app),
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
            "pin_order, copied_at, pin_key, alias, source_app FROM entries "
            "ORDER BY copied_at DESC, id DESC"
        ).fetchall()
        candidates = ("exact", "regex", "fuzzy") if mode == "mixed" else (mode,)
        matches = []
        effective_mode = candidates[-1]
        for candidate in candidates:
            matches = []
            for row in rows:
                display = row[10] or row[1]
                result = match(display, query, candidate)
                if result is None and row[10]:
                    display = row[1]
                    result = match(display, query, candidate)
                if result is not None:
                    matches.append((row, result, display))
            effective_mode = candidate
            if matches or mode != "mixed":
                break
        metric = {"first_copied": 5, "most_copied": 6}.get(sort_by, 8)
        def order(item):
            row, result, _display = item
            if row[2]:
                return (1 if pins_position == "bottom" else 0, row[7] or row[0], 0, 0)
            score = result[0] if query and effective_mode == "fuzzy" else 0
            return (0 if pins_position == "bottom" else 1, score, -row[metric], -row[0])
        return [row[:5] + (row[9], result[1], shown, row[11])
                for row, result, shown in sorted(matches, key=order)]

    def get(self, entry_id: int):
        row = self.db.execute(
            "SELECT text, kind, data, pinned, pin_key, alias FROM entries WHERE id=?",
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("text", "kind", "data", "pinned", "pin_key", "alias"), row))

    def metadata(self, entry_id: int):
        row = self.db.execute(
            "SELECT first_copied_at, copied_at, copy_count, source_app "
            "FROM entries WHERE id=?", (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("first_copied_at", "copied_at", "copy_count", "source_app"), row))

    def edit(self, entry_id: int, *, alias=_UNSET, content=None, pin_key=None):
        current = self.get(entry_id)
        if current is None:
            raise ValueError("This history item no longer exists")
        if alias is not _UNSET:
            if alias is not None and not isinstance(alias, str):
                raise ValueError("Alias must be text")
            alias = alias.strip() if alias is not None else None
            alias = alias or None
        if content is not None:
            if current["kind"] not in ("text", "rich"):
                raise ValueError("This content cannot be edited")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Content cannot be empty")
        if pin_key is not None:
            if not isinstance(pin_key, str):
                raise ValueError("Invalid pin shortcut")
            pin_key = pin_key.lower()
            if not current["pinned"] or pin_key not in PIN_KEYS:
                raise ValueError("Invalid pin shortcut")
            occupied = self.db.execute(
                "SELECT 1 FROM entries WHERE pinned=1 AND pin_key=? AND id<>?",
                (pin_key, entry_id),
            ).fetchone()
            if occupied:
                raise ValueError("This pin shortcut is already in use")
        fields = []
        values = []
        if alias is not _UNSET:
            fields.append("alias=?")
            values.append(alias)
        if content is not None and content != current["text"]:
            fields.extend(("text=?", "kind='text'", "data=NULL"))
            values.append(content)
        if pin_key is not None:
            fields.append("pin_key=?")
            values.append(pin_key)
        if not fields:
            return
        try:
            with self.db:
                self.db.execute(
                    "UPDATE entries SET " + ", ".join(fields) + " WHERE id=?",
                    (*values, entry_id),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("An item with this content already exists") from error

    def available_pin_keys(self, entry_id: int):
        occupied = {row[0] for row in self.db.execute(
            "SELECT pin_key FROM entries WHERE pinned=1 AND id<>? AND pin_key IS NOT NULL",
            (entry_id,),
        )}
        return [key for key in PIN_KEYS if key not in occupied]

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

    def move_pin(self, entry_id: int, step: int):
        pins = self.db.execute(
            "SELECT id, pin_order FROM entries WHERE pinned=1 ORDER BY pin_order, id"
        ).fetchall()
        position = next((index for index, pin in enumerate(pins) if pin[0] == entry_id), None)
        if position is None or not 0 <= position + step < len(pins):
            return False
        other_id, other_order = pins[position + step]
        own_order = pins[position][1]
        with self.db:
            self.db.execute("UPDATE entries SET pin_order=? WHERE id=?", (other_order, entry_id))
            self.db.execute("UPDATE entries SET pin_order=? WHERE id=?", (own_order, other_id))
        return True

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
