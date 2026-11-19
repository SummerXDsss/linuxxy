"""Copy from a real X11 window and show its desktop application icon."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from ui_smoke import activate, keys, screenshot, wait_for, window_id

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from settings import Settings


with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    desktop_dir = temp / 'applications'
    desktop_dir.mkdir()
    (desktop_dir / 'linuxxy-test-source.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=Test Copy Source\n'
        'Exec=/bin/true\nIcon=utilities-terminal\n'
        'StartupWMClass=LinuxxyTestSource\n'
    )
    settings = Settings(temp / 'linuxxy/settings.json')
    assert settings.get('show_application_icons') is False
    settings.set('show_application_icons', True)
    env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
               XDG_RUNTIME_DIR=directory, LINUXXY_TEST_WM_CLASS='LinuxxyTestSource',
               LINUXXY_TEST_XID=str(temp / 'target-xid'),
               LINUXXY_TEST_VALUE=str(temp / 'target-value'),
               LINUXXY_TEST_COMMAND=str(temp / 'target-command'))
    target = subprocess.Popen([sys.executable, str(ROOT / 'tests/paste_target.py')],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    app = None
    try:
        target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text()
                                  if (temp / 'target-xid').exists() else None))
        app = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        activate(target_xid)
        keys('Control_L', 'c')

        def source_saved():
            database = temp / 'linuxxy/history.sqlite'
            if not database.exists():
                return False
            with sqlite3.connect(database) as db:
                row = db.execute('SELECT source_app FROM entries WHERE text=?',
                                 ('hello linuxxy clipboard',)).fetchone()
            return row and row[0] == 'LinuxxyTestSource'

        wait_for(source_saved)
        keys('Shift_L', 'Super_L', 'v')
        popup = wait_for(lambda: window_id('Linuxxy'))
        screenshot(popup, 'ui_application_icon.png')
        assert app.poll() is None
        print('Source application captured and icon popup screenshot saved')
    finally:
        target.terminate()
        if app:
            app.terminate()
        target.communicate(timeout=5)
        if app:
            stdout, stderr = app.communicate(timeout=5)
            assert b'Traceback' not in stdout + stderr, (stdout + stderr).decode(errors='replace')[-1200:]
