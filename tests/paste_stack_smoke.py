"""Exercise a three-item paste queue across real X11 windows."""

import atexit
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk

from ui_smoke import activate, keys, screenshot, wait_for, window_id


ROOT = Path(__file__).resolve().parents[1]


def main():
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    original = clipboard.wait_for_text()
    def restore():
        if original is not None:
            clipboard.set_text(original, -1)
            clipboard.store()
    atexit.register(restore)
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                   XDG_RUNTIME_DIR=directory,
                   LINUXXY_TEST_XID=str(temp / 'target-xid'),
                   LINUXXY_TEST_VALUE=str(temp / 'target-value'),
                   LINUXXY_TEST_COMMAND=str(temp / 'target-command'))
        app = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        target = subprocess.Popen([sys.executable, str(ROOT / 'tests/paste_target.py')], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text()
                                      if (temp / 'target-xid').exists() else None))
            database = temp / 'linuxxy/history.sqlite'
            for value in ('Queue A', 'Queue B', 'Queue C'):
                clipboard.set_text(value, -1)
                clipboard.store()
                def stored():
                    if not database.exists():
                        return False
                    with sqlite3.connect(database) as db:
                        return db.execute('SELECT 1 FROM entries WHERE text=?', (value,)).fetchone()
                wait_for(stored)
            activate(target_xid)
            keys('Shift_L', 'Super_L', 'v')
            popup = wait_for(lambda: window_id('Linuxxy'))
            keys('Down')
            keys('Shift_L', 'Down')
            keys('Shift_L', 'Down')
            screenshot(popup, 'ui_paste_queue.png')
            keys('Control_L', 'Shift_L', 'Return')
            wait_for(lambda: not window_id('Linuxxy'))
            wait_for(lambda: clipboard.wait_for_text() == 'Queue C')
            for pasted, next_value in (('Queue C', 'Queue B'),
                                       ('Queue B', 'Queue A'),
                                       ('Queue A', 'Queue A')):
                (temp / 'target-command').write_text('clear')
                wait_for(lambda: (temp / 'target-value').read_text() == '')
                activate(target_xid)
                keys('Control_L', 'v')
                try:
                    wait_for(lambda: (temp / 'target-value').read_text() == pasted)
                except AssertionError:
                    raise AssertionError(
                        f'Expected {pasted!r}, got {(temp / "target-value").read_text()!r}; '
                        f'clipboard is {clipboard.wait_for_text()!r}'
                    )
                wait_for(lambda: clipboard.wait_for_text() == next_value)
            screenshot(target_xid, 'ui_paste_queue_done.png')
            activate(target_xid)
            keys('Shift_L', 'Super_L', 'v')
            wait_for(lambda: window_id('Linuxxy'))
            keys('Down')
            keys('Shift_L', 'Down')
            keys('Control_L', 'Shift_L', 'Return')
            wait_for(lambda: not window_id('Linuxxy'))
            clipboard.set_text('New external copy', -1)
            clipboard.store()
            def external_stored():
                with sqlite3.connect(database) as db:
                    return db.execute('SELECT 1 FROM entries WHERE text=?',
                                      ('New external copy',)).fetchone()
            wait_for(external_stored)
            (temp / 'target-command').write_text('clear')
            wait_for(lambda: (temp / 'target-value').read_text() == '')
            activate(target_xid)
            keys('Control_L', 'v')
            wait_for(lambda: (temp / 'target-value').read_text() == 'New external copy')
            time.sleep(.35)
            assert clipboard.wait_for_text() == 'New external copy'
            print('Paste queue passed; screenshots saved')
        finally:
            target.terminate()
            app.terminate()
            target.communicate(timeout=5)
            stdout, stderr = app.communicate(timeout=5)
            if stdout:
                print(stdout.decode(errors='replace')[-1200:])
            if stderr:
                print(stderr.decode(errors='replace')[-1200:])


if __name__ == '__main__':
    main()
