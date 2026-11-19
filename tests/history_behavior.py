"""Exercise legacy history migration, copy counts, sorting, and stable pins."""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'history.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE entries (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, '
                   'copied_at REAL NOT NULL, pinned INTEGER NOT NULL DEFAULT 0)')
        db.executemany('INSERT INTO entries(text, copied_at, pinned) VALUES (?, ?, 0)',
                       [('old', 100), ('new', 200)])

    history = History(path)
    try:
        history.add('old')
        history.add('third', 'Gnome-terminal')
        assert history.list()[0][8] == 'Gnome-terminal'
        history.add_rich('formatted', b'<b>formatted</b>')
        history.add('formatted')
        rich_row = next(row for row in history.list() if row[1] == 'formatted')
        assert rich_row[3:5] == ('rich', b'<b>formatted</b>')
        history.delete(rich_row[0])
        metadata = history.db.execute(
            'SELECT first_copied_at, copy_count FROM entries WHERE text="old"'
        ).fetchone()
        assert metadata == (100, 2), metadata

        labels = lambda sort: [row[1] for row in history.list(sort_by=sort)]
        assert labels('last_copied') == ['third', 'old', 'new']
        assert labels('first_copied') == ['third', 'new', 'old']
        assert labels('most_copied') == ['old', 'third', 'new']

        entry_id = next(row[0] for row in history.list() if row[1] == 'new')
        history.pin(entry_id, True)
        history.add('new')
        history.add('old')
        assert labels('last_copied')[0] == 'new'
        assert [row[1] for row in history.list(pins_position='bottom')][-1] == 'new'
        assert history.list()[0][5] == 'b'
        history.close()
        history = History(path)
        assert history.list()[0][5] == 'b'
        history.pin(entry_id, False)
        old_id = next(row[0] for row in history.list() if row[1] == 'old')
        history.pin(old_id, True)
        assert history.list()[0][5] == 'b'
        history.pin(entry_id, True)
        third_id = next(row[0] for row in history.list() if row[1] == 'third')
        history.pin(third_id, True)
        assert history.move_pin(third_id, -1)
        assert [row[1] for row in history.list()] == ['old', 'third', 'new']
        assert not history.move_pin(old_id, -1)
        assert {row[1]: row[5] for row in history.list()} == {
            'old': 'b', 'new': 'c', 'third': 'd'
        }
        history.add('third')
        history.close()
        history = History(path)
        assert [row[1] for row in history.list()] == ['old', 'third', 'new']
        assert history.get(third_id) is not None
        assert next(row[8] for row in history.list() if row[1] == 'third') == 'Gnome-terminal'
    finally:
        history.close()

print('History migration, sorting, and pins passed')
