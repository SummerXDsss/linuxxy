#!/usr/bin/env python3
"""Install Linuxxy as a per-user desktop application."""

import argparse
import os
import shlex
import shutil
import sys
from pathlib import Path


PROGRAM_FILES = ("linuxxy.py", "history.py", "settings.py", "autostart.py", "install.py",
                 "x11.py", "x11_clipboard.py", "README.md", "LICENSE",
                 "LICENSE-Maccy")


def desktop_quote(path):
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def install(prefix):
    source = Path(__file__).resolve().parent
    app_dir = prefix / "share" / "linuxxy"
    launcher = prefix / "bin" / "linuxxy"
    desktop = prefix / "share" / "applications" / "linuxxy.desktop"
    app_dir.mkdir(parents=True, exist_ok=True)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    for name in PROGRAM_FILES:
        shutil.copy2(source / name, app_dir / name)
    launcher.write_text(
        "#!/bin/sh\n" +
        f"exec {shlex.quote(sys.executable)} {shlex.quote(str(app_dir / 'linuxxy.py'))} \"$@\"\n"
    )
    launcher.chmod(0o755)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=Linuxxy\n"
        "Comment=Search and reuse clipboard history\n"
        f"Exec={desktop_quote(launcher)}\n"
        f"TryExec={launcher}\n"
        "Icon=edit-paste\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "StartupNotify=false\n"
    )
    print(f"Installed Linuxxy in {app_dir}")
    print(f"Open it from your app menu or run {launcher}")


def uninstall(prefix):
    app_dir = prefix / "share" / "linuxxy"
    launcher = prefix / "bin" / "linuxxy"
    desktop = prefix / "share" / "applications" / "linuxxy.desktop"
    for path in (launcher, desktop):
        path.unlink(missing_ok=True)
    if app_dir.exists():
        shutil.rmtree(app_dir)
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    (config_home / "autostart" / "linuxxy.desktop").unlink(missing_ok=True)
    print("Uninstalled Linuxxy. Clipboard history and preferences were kept.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local",
                        help="installation location (default: ~/.local)")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    (uninstall if args.uninstall else install)(args.prefix.expanduser().resolve())
