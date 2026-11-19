"""Verify a user install launches from its app-menu files and can be removed."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from gi.repository import Gio

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    prefix = temp / 'prefix'
    command = [sys.executable, str(ROOT / 'install.py'), '--prefix', str(prefix)]
    subprocess.run(command, check=True, capture_output=True)
    launcher = prefix / 'bin/linuxxy'
    desktop = prefix / 'share/applications/linuxxy.desktop'
    installed = prefix / 'share/linuxxy'
    assert launcher.exists() and os.access(launcher, os.X_OK)
    assert f'Exec="{launcher}"' in desktop.read_text()
    desktop_app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
    assert desktop_app and str(launcher) in desktop_app.get_commandline()
    assert (installed / 'LICENSE-Maccy').exists()

    env = dict(os.environ, XDG_CONFIG_HOME=str(temp / 'config'),
               XDG_DATA_HOME=str(temp / 'data'), XDG_RUNTIME_DIR=str(temp),
               XDG_SESSION_TYPE='x11')
    app = subprocess.Popen([str(launcher)], env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
    try:
        database = temp / 'data/linuxxy/history.sqlite'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not database.exists() and app.poll() is None:
            time.sleep(.05)
        assert database.exists() and app.poll() is None, app.communicate() if app.poll() is not None else ''
    finally:
        if app.poll() is None:
            app.terminate()
        app.communicate(timeout=5)

    subprocess.run([sys.executable, str(installed / 'install.py'), '--prefix', str(prefix),
                    '--uninstall'], check=True, capture_output=True, env=env)
    assert not launcher.exists() and not desktop.exists() and not installed.exists()
    assert database.exists()

print('Installed launcher, app-menu entry, and uninstall passed')
