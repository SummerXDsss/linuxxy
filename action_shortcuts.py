"""Popup-local shortcut parsing, recording, and event matching."""

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk


MODIFIERS = (
    ("Ctrl", Gdk.ModifierType.CONTROL_MASK),
    ("Alt", Gdk.ModifierType.MOD1_MASK),
    ("Shift", Gdk.ModifierType.SHIFT_MASK),
    ("Super", Gdk.ModifierType.MOD4_MASK),
)
MODIFIER_MASK = sum(int(mask) for _, mask in MODIFIERS)
ALIASES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "option": "Alt",
           "shift": "Shift", "super": "Super", "meta": "Super"}
KEY_ALIASES = {"enter": "Return", "return": "Return", "esc": "Escape",
               "del": "Delete", "delete": "Delete", "backspace": "BackSpace",
               "space": "space", "up": "Up", "down": "Down", "tab": "Tab"}


def parse_action_shortcut(value):
    if not isinstance(value, str):
        raise ValueError("Shortcut must be text")
    if not value.strip():
        return None
    parts = [part.strip() for part in value.split("+")]
    if any(not part for part in parts):
        raise ValueError("Use a shortcut such as Alt+P or Ctrl+Space")
    modifiers = 0
    for part in parts[:-1]:
        name = ALIASES.get(part.casefold())
        if name is None:
            raise ValueError("Unknown shortcut modifier")
        mask = int(dict(MODIFIERS)[name])
        if modifiers & mask:
            raise ValueError("Shortcut modifier is repeated")
        modifiers |= mask
    key_name = KEY_ALIASES.get(parts[-1].casefold(), parts[-1])
    keyval = Gdk.keyval_from_name(key_name)
    if not keyval:
        keyval = Gdk.keyval_from_name(key_name.lower())
    if keyval in (0, Gdk.KEY_VoidSymbol, Gdk.KEY_Escape):
        raise ValueError("Unknown or reserved shortcut key")
    keyval = Gdk.keyval_to_lower(keyval)
    name = Gdk.keyval_name(keyval) or ""
    if name.startswith(("Shift_", "Control_", "Alt_", "Super_", "Meta_")):
        raise ValueError("Shortcut needs a non-modifier key")
    if not modifiers & int(Gdk.ModifierType.CONTROL_MASK |
                           Gdk.ModifierType.MOD1_MASK |
                           Gdk.ModifierType.MOD4_MASK) and \
            keyval < 128 and chr(keyval).isalnum():
        raise ValueError("Letters and digits need Ctrl, Alt, or Super")
    return keyval, modifiers


def normalize_action_shortcut(value):
    parsed = parse_action_shortcut(value)
    if parsed is None:
        return ""
    keyval, modifiers = parsed
    name = Gdk.keyval_name(keyval)
    if keyval == Gdk.KEY_space:
        name = "Space"
    elif len(name) == 1 and name.isalpha():
        name = name.upper()
    return "+".join([label for label, mask in MODIFIERS if modifiers & int(mask)] + [name])


def action_shortcut_from_event(event):
    key_name = Gdk.keyval_name(event.keyval) or ""
    if key_name.startswith(("Shift_", "Control_", "Alt_", "Super_", "Meta_")):
        return None
    modifiers = int(event.state) & MODIFIER_MASK
    value = "+".join([label for label, mask in MODIFIERS if modifiers & int(mask)] +
                     [key_name])
    return normalize_action_shortcut(value)


def matches_action_shortcut(value, event):
    parsed = parse_action_shortcut(value)
    return bool(parsed and parsed == (Gdk.keyval_to_lower(event.keyval),
                                      int(event.state) & MODIFIER_MASK))


def validate_action_shortcuts(open_shortcut, actions, pin_keys):
    """Reject action keys that would shadow another popup command."""
    parsed = [parse_action_shortcut(value) for value in actions]
    active = [shortcut for shortcut in parsed if shortcut is not None]
    if len(active) != len(set(active)):
        raise ValueError("Two actions use the same shortcut")
    if parse_action_shortcut(open_shortcut) in active:
        raise ValueError("An action uses the opening shortcut")
    reserved = ["F2", "Alt+Up", "Alt+Down", "Shift+Up", "Shift+Down",
                "Ctrl+Return", "Ctrl+Shift+Return", "Ctrl+comma",
                "Ctrl+Alt+Delete", "Ctrl+Alt+Shift+Delete"]
    reserved += [f"{modifier}+{key}" for modifier in ("Ctrl", "Alt")
                 for key in "123456789"]
    reserved += [f"{modifier}+{key}" for modifier in ("Ctrl", "Alt", "Alt+Shift")
                 for key in pin_keys]
    reserved_specs = {parse_action_shortcut(value) for value in reserved}
    if any(shortcut in reserved_specs for shortcut in active):
        raise ValueError("An action shortcut is already used by the popup")
