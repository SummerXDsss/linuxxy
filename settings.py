"""Validated, persistent preferences for Linuxxy."""

import json
import os
from pathlib import Path


DEFAULTS = {
    "shortcut": "Super+Shift+V",
    "paste_by_default": False,
    "remove_formatting_by_default": False,
    "history_size": 200,
    "check_interval_ms": 500,
    "clear_on_quit": False,
    "popup_at_cursor": True,
    "launch_at_login": False,
    "search_mode": "exact",
    "sort_by": "last_copied",
    "open_preview_automatically": True,
    "preview_delay_ms": 1500,
    "highlight_match": "bold",
    "pins_position": "top",
    "save_text": True,
    "save_images": True,
    "save_files": True,
    "show_footer": True,
}


class Settings:
    def __init__(self, path=None):
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.path = Path(path) if path else config_home / "linuxxy" / "settings.json"
        self.values = DEFAULTS.copy()
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in DEFAULTS:
                        try:
                            self.set(key, value, save=False)
                        except ValueError:
                            pass
        except (FileNotFoundError, ValueError, OSError, TypeError):
            pass

    def get(self, key):
        return self.values[key]

    def set(self, key, value, save=True):
        if key not in DEFAULTS:
            raise KeyError(key)
        if key == "shortcut":
            from x11 import parse_shortcut
            parse_shortcut(value)
        elif key == "search_mode":
            if value not in ("exact", "fuzzy", "regex", "mixed"):
                raise ValueError("Invalid search mode")
        elif key == "sort_by":
            if value not in ("last_copied", "first_copied", "most_copied"):
                raise ValueError("Invalid sort order")
        elif key == "highlight_match":
            if value not in ("bold", "italic", "underline", "color"):
                raise ValueError("Invalid highlight style")
        elif key == "pins_position":
            if value not in ("top", "bottom"):
                raise ValueError("Invalid pins position")
        elif key in ("history_size", "check_interval_ms", "preview_delay_ms"):
            maximum = 10000 if key == "history_size" else 100000 if key == "preview_delay_ms" else 5000
            minimum = 200 if key == "preview_delay_ms" else 1
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Invalid {key}")
        elif type(value) is not bool:
            raise ValueError(f"Invalid {key}")
        self.values[key] = value
        if save:
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.values, indent=2) + "\n")
        os.replace(temporary, self.path)
