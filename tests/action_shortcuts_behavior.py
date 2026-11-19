"""Check local shortcut parsing, conflicts, and saved settings."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from action_shortcuts import normalize_action_shortcut, parse_action_shortcut, validate_action_shortcuts
from history import PIN_KEYS
from settings import Settings


assert normalize_action_shortcut('alt+delete') == 'Alt+Delete'
assert normalize_action_shortcut('control+space') == 'Ctrl+Space'
assert normalize_action_shortcut('super+shift+v') == 'Shift+Super+V'
for invalid in ('P', 'Alt+Alt+P', 'Ctrl+Escape', 'Ctrl+NoSuchKey'):
    try:
        parse_action_shortcut(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Accepted invalid shortcut: {invalid}')

validate_action_shortcuts('Super+Shift+V', ('Alt+P', 'Alt+Delete', 'Ctrl+Space'), PIN_KEYS)
for actions in (('Alt+P', 'Alt+P', 'Ctrl+Space'),
                ('Alt+B', 'Alt+Delete', 'Ctrl+Space'),
                ('Alt+P', 'Alt+Delete', 'Super+Shift+V')):
    try:
        validate_action_shortcuts('Super+Shift+V', actions, PIN_KEYS)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Accepted conflicting shortcuts: {actions}')

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'settings.json'
    settings = Settings(path)
    assert settings.get('preview_shortcut') == 'Ctrl+Space'
    settings.set('preview_shortcut', 'Ctrl+F3')
    settings.set('pin_shortcut', '')
    reopened = Settings(path)
    assert reopened.get('preview_shortcut') == 'Ctrl+F3'
    assert reopened.get('pin_shortcut') == ''

print('Action shortcut parsing, conflicts, and settings passed')
