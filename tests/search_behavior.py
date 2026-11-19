"""Check ranked fuzzy search, mixed fallback, and visible match snippets."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from search import match, snippet


with tempfile.TemporaryDirectory() as directory:
    history = History(Path(directory) / 'history.sqlite')
    try:
        history.add('abc neat')
        history.add('a long b long c')
        assert [row[1] for row in history.list('abc', 'exact')] == ['abc neat']
        assert [row[1] for row in history.list('abc', 'mixed')] == ['abc neat']
        fuzzy = history.list('abc', 'fuzzy')
        assert [row[1] for row in fuzzy] == ['abc neat', 'a long b long c']
        assert fuzzy[0][6] == [(0, 3)]
        assert [row[1] for row in history.list('^A.*c', 'regex')] == [
            'a long b long c', 'abc neat'
        ]
    finally:
        history.close()

assert match('one two three', 'ott', 'fuzzy')[1] == [(0, 1), (4, 5), (8, 9)]
assert match('a' * 300 + 'abc', 'abc', 'fuzzy')[1] == [(300, 303)]
assert match('hello', '[', 'regex') is None
long_text = 'a' * 180 + '<match>&'
visible, ranges = snippet(long_text, [(180, 187)])
assert '<match>' in visible and visible[ranges[0][0]:ranges[0][1]] == '<match>'

print('Search ranking, modes, and snippets passed')
