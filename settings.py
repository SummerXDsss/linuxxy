"""Validated, persistent preferences for Linuxxy."""

import json
import os
from pathlib import Path


DEFAULTS = {
    "shortcut": "Super+Shift+V",
    "pin_shortcut": "Alt+P",
    "delete_shortcut": "Alt+Delete",
    "preview_shortcut": "Ctrl+Space",
    "paste_by_default": False,
    "remove_formatting_by_default": False,
    "history_size": 200,
    "check_interval_ms": 500,
    "clear_on_quit": False,
    "clear_system_clipboard": False,
    "suppress_clear_confirmation": False,
    "monitoring_paused": False,
    "popup_position": "cursor",
    "popup_last_position": None,
    "launch_at_login": False,
    "search_mode": "exact",
    "sort_by": "last_copied",
    "open_preview_automatically": True,
    "preview_delay_ms": 1500,
    "preview_width": 400,
    "popup_width": 440,
    "popup_max_height": 800,
    "highlight_match": "bold",
    "image_max_height": 40,
    "show_hex_color_swatch": True,
    "show_special_symbols": True,
    "show_search_field": True,
    "search_visibility": "always",
    "pins_position": "top",
    "save_text": True,
    "save_images": True,
    "save_files": True,
    "show_footer": True,
    "show_application_icons": False,
    "show_title": True,
    "show_tray_icon": True,
    "tray_icon": "clipboard",
    "show_recent_copy_in_tray": False,
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
                if "popup_position" not in data and type(data.get("popup_at_cursor")) is bool:
                    self.values["popup_position"] = (
                        "cursor" if data["popup_at_cursor"] else "screen_center"
                    )
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
        elif key in ("pin_shortcut", "delete_shortcut", "preview_shortcut"):
            from action_shortcuts import normalize_action_shortcut
            value = normalize_action_shortcut(value)
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
        elif key == "search_visibility":
            if value not in ("always", "during_search"):
                raise ValueError("Invalid search visibility")
        elif key == "popup_position":
            if value not in ("cursor", "status_icon", "active_window", "screen_center",
                             "last_position"):
                raise ValueError("Invalid popup position")
        elif key == "popup_last_position":
            if value is not None and (type(value) is not list or len(value) != 2 or
                                      any(type(coordinate) is not int for coordinate in value)):
                raise ValueError("Invalid last popup position")
        elif key == "image_max_height":
            if type(value) is not int or not 1 <= value <= 200:
                raise ValueError("Invalid image height")
        elif key in ("preview_width", "popup_width"):
            maximum = 800 if key == "preview_width" else 1000
            minimum = 200 if key == "preview_width" else 320
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Invalid {key}")
        elif key == "popup_max_height":
            if type(value) is not int or not 180 <= value <= 2000:
                raise ValueError("Invalid popup height limit")
        elif key == "tray_icon":
            if value not in ("clipboard", "scissors", "paperclip", "copy"):
                raise ValueError("Invalid tray icon")
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
