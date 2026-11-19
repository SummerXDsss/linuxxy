"""Check accepted color formats and reject ordinary clipboard text."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from color_swatch import rgba


assert rgba('#abc') == 0xaabbccff
assert rgba('#abcd') == 0xaabbccdd
assert rgba('#1A2b3C') == 0x1a2b3cff
assert rgba('#1A2b3C80') == 0x1a2b3c80
for value in ('abc', '#12', '#12345', '#123456789', '#123456 is a color', 'test #abc'):
    assert rgba(value) is None, value
print('Hex color recognition passed')
