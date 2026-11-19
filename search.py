"""Search clipboard titles and return the character ranges that matched."""

from bisect import bisect_right
from collections import defaultdict
import re


def match(text, query, mode):
    """Return (fuzzy score, ranges) or None when the query does not match."""
    if not query:
        return 0, []
    if mode == "fuzzy":
        return _fuzzy(text, query)
    pattern = query if mode == "regex" else re.escape(query)
    try:
        found = re.search(pattern, text, re.IGNORECASE)
    except re.error:
        return None
    if found is None:
        return None
    return 0, [found.span()] if found.start() != found.end() else []


def _fuzzy(text, query):
    text = text[:5000]
    needle = [character.casefold() for character in query]
    if len(needle) > len(text):
        return None
    positions = defaultdict(list)
    for index, character in enumerate(text):
        positions[character.casefold()].append(index)
    if any(character not in positions for character in needle):
        return None
    starts = positions.get(needle[0], [])
    best = None
    for start in starts:
        if best is not None and start / 10 - 2 * len(needle) - 3 * (len(needle) - 1) >= best[0]:
            break
        indexes = [start]
        for character in needle[1:]:
            choices = positions.get(character, [])
            next_index = bisect_right(choices, indexes[-1])
            if next_index == len(choices):
                break
            indexes.append(choices[next_index])
        if len(indexes) != len(needle):
            continue
        span = indexes[-1] - start + 1
        if span > max(80, len(needle) * 8):
            continue
        boundaries = sum(index == 0 or not text[index - 1].isalnum() for index in indexes)
        contiguous = sum(right == left + 1 for left, right in zip(indexes, indexes[1:]))
        score = 4 * (span - len(needle)) + start / 10 - 2 * boundaries - 3 * contiguous
        if best is None or score < best[0]:
            best = score, indexes
    if best is None:
        return None
    score, indexes = best
    ranges = []
    for index in indexes:
        if ranges and ranges[-1][1] == index:
            ranges[-1] = ranges[-1][0], index + 1
        else:
            ranges.append((index, index + 1))
    return score, ranges


def snippet(text, ranges, limit=160):
    """Keep the first match visible in a short, single-line title."""
    text = ''.join(' ' if character.isspace() else character for character in text)
    first = next((start for start, _ in ranges if start < len(text)), 0)
    start = max(0, first - 40) if first >= limit else 0
    end = min(len(text), start + limit)
    prefix = '…' if start else ''
    suffix = '…' if end < len(text) else ''
    visible = prefix + text[start:end] + suffix
    offset = len(prefix) - start
    shown = [(max(left, start) + offset, min(right, end) + offset)
             for left, right in ranges if right > start and left < end]
    return visible, shown


def visible_title(text, show_special_symbols=True):
    """Display whitespace without shifting character indexes used by search."""
    if not show_special_symbols:
        return text
    characters = list(text)
    for index, character in enumerate(characters):
        if character != ' ':
            break
        characters[index] = '·'
    for index in range(len(characters) - 1, -1, -1):
        if characters[index] != ' ':
            break
        characters[index] = '·'
    return ''.join(characters).replace('\n', '⏎').replace('\t', '⇥')
