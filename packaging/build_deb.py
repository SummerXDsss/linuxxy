#!/usr/bin/env python3
"""Build a system-installable Debian package for Linuxxy."""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM_FILES = (
    "linuxxy.py", "glass.py", "i18n.py", "history.py", "settings.py",
    "autostart.py", "x11.py", "x11_clipboard.py", "paste_keys.py",
    "color_swatch.py", "action_shortcuts.py", "search.py", "LICENSE",
)
DEPENDENCIES = (
    "python3", "python3-gi", "gir1.2-gtk-3.0", "python3-xlib",
    "python3-cairo", "python3-pil",
)


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)


def build(output_dir, version):
    if not version or any(char.isspace() for char in version) or "/" in version:
        raise ValueError("Invalid Debian package version")
    output_dir.mkdir(parents=True, exist_ok=True)
    package = output_dir / f"linuxxy_{version}_all.deb"
    with tempfile.TemporaryDirectory(prefix="linuxxy-deb-") as temporary:
        stage = Path(temporary) / "linuxxy"
        app_dir = stage / "usr/share/linuxxy"
        app_dir.mkdir(parents=True)
        for name in PROGRAM_FILES:
            shutil.copyfile(ROOT / name, app_dir / name)
            (app_dir / name).chmod(0o644)
        write(stage / "usr/bin/linuxxy",
              '#!/bin/sh\nexec /usr/bin/python3 /usr/share/linuxxy/linuxxy.py "$@"\n',
              executable=True)
        write(stage / "usr/share/applications/linuxxy.desktop",
              "[Desktop Entry]\n"
              "Version=1.0\nType=Application\nName=Linuxxy\n"
              "Comment=Search and reuse clipboard history\n"
              "Comment[zh_CN]=搜索并重用剪贴板历史\n"
              "Exec=/usr/bin/linuxxy\nTryExec=/usr/bin/linuxxy\nIcon=edit-paste\n"
              "Terminal=false\nCategories=Utility;\nStartupNotify=false\n")
        docs = stage / "usr/share/doc/linuxxy"
        docs.mkdir(parents=True)
        shutil.copyfile(ROOT / "README.md", docs / "README")
        shutil.copyfile(ROOT / "LICENSE", docs / "LICENSE")
        shutil.copyfile(ROOT / "LICENSE-Maccy", docs / "LICENSE-Maccy")
        for item in docs.iterdir():
            item.chmod(0o644)
        write(stage / "DEBIAN/control",
              "Package: linuxxy\n"
              f"Version: {version}\n"
              "Section: utils\nPriority: optional\nArchitecture: all\n"
              "Maintainer: SummerXDsss\n"
              f"Depends: {', '.join(DEPENDENCIES)}\n"
              "Recommends: fonts-noto-cjk\n"
              "Homepage: https://github.com/SummerXDsss/linuxxy\n"
              "Description: Searchable clipboard history for X11 desktops\n"
              " Linuxxy keeps text, image, and file clipboard history and offers\n"
              " keyboard search, pinned items, and a GTK 3 tray interface.\n")
        for directory in (stage, *stage.rglob("*")):
            if directory.is_dir():
                directory.chmod(0o755)
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group",
                        str(stage), str(package)], check=True)
    return package


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.1.1")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(args.output_dir.resolve(), args.version))
