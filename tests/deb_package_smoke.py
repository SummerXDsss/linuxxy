"""Check the Debian package layout and its installed entry points."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from gi.repository import GLib


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "linuxxy.py", "glass.py", "i18n.py", "history.py", "settings.py",
    "autostart.py", "x11.py", "x11_clipboard.py", "paste_keys.py",
    "color_swatch.py", "action_shortcuts.py", "search.py",
)

with tempfile.TemporaryDirectory(prefix="linuxxy-deb-test-") as directory:
    temp = Path(directory)
    subprocess.run([sys.executable, str(ROOT / "packaging/build_deb.py"),
                    "--output-dir", str(temp)], check=True, capture_output=True)
    package = temp / "linuxxy_0.1.1_all.deb"
    fields = subprocess.check_output(
        ["dpkg-deb", "--field", str(package)], text=True)
    assert "Package: linuxxy\n" in fields
    assert "Architecture: all\n" in fields
    assert "Version: 0.1.1\n" in fields
    for dependency in ("python3-gi", "gir1.2-gtk-3.0", "python3-xlib",
                       "python3-cairo", "python3-pil"):
        assert dependency in fields
    stage = temp / "stage"
    subprocess.run(["dpkg-deb", "--extract", str(package), str(stage)], check=True)
    launcher = stage / "usr/bin/linuxxy"
    assert os.access(launcher, os.X_OK)
    assert "/usr/share/linuxxy/linuxxy.py" in launcher.read_text()
    app_dir = stage / "usr/share/linuxxy"
    for name in MODULES:
        assert (app_dir / name).read_bytes() == (ROOT / name).read_bytes()
    assert (app_dir / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    desktop = stage / "usr/share/applications/linuxxy.desktop"
    desktop_entry = GLib.KeyFile()
    desktop_entry.load_from_file(str(desktop), GLib.KeyFileFlags.NONE)
    assert desktop_entry.get_string("Desktop Entry", "Exec") == "/usr/bin/linuxxy"
    assert desktop_entry.get_string("Desktop Entry", "TryExec") == "/usr/bin/linuxxy"
    assert desktop_entry.get_locale_string("Desktop Entry", "Comment", "zh_CN")
    if shutil.which("desktop-file-validate"):
        subprocess.run(["desktop-file-validate", str(desktop)], check=True)
    docs = stage / "usr/share/doc/linuxxy"
    for name in ("LICENSE", "LICENSE-Maccy"):
        assert (docs / name).read_bytes() == (ROOT / name).read_bytes()
    subprocess.run([sys.executable, "-m", "py_compile",
                    *(str(app_dir / name) for name in MODULES)], check=True)

print("Debian package control, files, launcher, desktop entry, and Python passed")
