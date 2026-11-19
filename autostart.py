"""Manage the freedesktop desktop entry used for login startup."""

import os
import sys
from pathlib import Path


def _quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def set_enabled(enabled):
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = config_home / "autostart" / "linuxxy.desktop"
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    command = f"{_quote(sys.executable)} {_quote(Path(__file__).with_name('linuxxy.py').resolve())}"
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=Linuxxy\n"
        f"Exec={command}\nIcon=edit-paste\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
    )
