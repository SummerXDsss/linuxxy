"""Exercise editable aliases, content, and pin shortcuts across restarts."""

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from history import History


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'history.sqlite'
    history = History(path)
    try:
        history.add('original content')
        first = history.list()[0][0]
        history.pin(first, True)
        history.edit(first, alias='Project note', pin_key='x')
        assert history.get(first)['pin_key'] == 'x'
        assert history.list()[0][7] == 'Project note'
        assert history.list('Project')[0][7] == 'Project note'
        assert history.list('original')[0][7] == 'original content'
        history.edit(first, content='revised content')
        assert history.get(first)['text'] == 'revised content'
        assert history.list()[0][7] == 'Project note'

        history.add_rich('formatted', b'<b>formatted</b>')
        rich = next(row[0] for row in history.list() if row[1] == 'formatted')
        history.edit(rich, alias='Styled note')
        assert history.get(rich)['kind'] == 'rich'
        history.edit(rich, content='plain revision')
        assert history.get(rich)['kind'] == 'text'
        assert history.get(rich)['data'] is None

        history.add('another item')
        second = next(row[0] for row in history.list() if row[1] == 'another item')
        history.pin(second, True)
        try:
            history.edit(second, alias='Should roll back', content='revised content', pin_key='x')
        except ValueError:
            pass
        else:
            raise AssertionError('Duplicate pin shortcut was accepted')
        assert history.get(second)['alias'] is None
        try:
            history.edit(second, content='revised content')
        except ValueError:
            pass
        else:
            raise AssertionError('Duplicate content was accepted')
        assert history.get(second)['text'] == 'another item'

        history.add_files(['file:///tmp/example.txt'])
        files = next(row[0] for row in history.list() if row[3] == 'files')
        history.edit(files, alias='Report attachment')
        assert history.list()[0][7] == 'Project note'
        assert history.list('Report')[0][7] == 'Report attachment'
        try:
            history.edit(files, content='not a file')
        except ValueError:
            pass
        else:
            raise AssertionError('File content editing was accepted')
        history.close()
        history = History(path)
        assert history.get(first)['alias'] == 'Project note'
        assert history.get(first)['pin_key'] == 'x'
        assert history.get(files)['alias'] == 'Report attachment'
    finally:
        history.close()

print('Editor persistence and validation passed')
