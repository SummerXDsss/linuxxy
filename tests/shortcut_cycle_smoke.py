"""Hold the opening shortcut to cycle and select clipboard history."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk
from Xlib import X, XK, display
from Xlib.ext import xtest

from ui_smoke import activate, keys, screenshot_root, wait_for, window_id

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from settings import Settings


def key_event(name, down):
    connection = display.Display()
    keycode = connection.keysym_to_keycode(XK.string_to_keysym(name))
    assert keycode, name
    xtest.fake_input(connection, X.KeyPress if down else X.KeyRelease, keycode)
    connection.sync()
    connection.close()
    time.sleep(.06)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                   XDG_RUNTIME_DIR=directory, LINUXXY_TEST_XID=str(temp / 'target-xid'),
                   LINUXXY_TEST_VALUE=str(temp / 'target-value'),
                   LINUXXY_TEST_COMMAND=str(temp / 'target-command'))
        history = History(temp / 'linuxxy/history.sqlite')
        for item in ('Blue item', 'Green item', 'Red item'):
            history.add(item)
        history.close()
        Settings(temp / 'linuxxy/settings.json').set('open_preview_automatically', False)
        target = subprocess.Popen([sys.executable, str(ROOT / 'tests/paste_target.py')],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        app = None
        try:
            target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text()
                                      if (temp / 'target-xid').exists() else None))
            app = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(.5)
            assert app.poll() is None
            activate(target_xid)

            # A single shortcut press opens the normal searchable popup.
            for name in ('Shift_L', 'Super_L', 'v'):
                key_event(name, True)
            key_event('v', False)
            popup = wait_for(lambda: window_id('Linuxxy'))
            key_event('Super_L', False)
            key_event('Shift_L', False)
            time.sleep(.2)
            assert window_id('Linuxxy') == popup
            keys('Escape')
            wait_for(lambda: window_id('Linuxxy') is None)

            # Press the main key again while holding the modifiers to cycle.
            activate(target_xid)
            for name in ('Shift_L', 'Super_L', 'v'):
                key_event(name, True)
            key_event('v', False)
            wait_for(lambda: window_id('Linuxxy'))
            key_event('v', True)
            key_event('v', False)
            screenshot_root('ui_shortcut_cycle.png')
            key_event('Super_L', False)
            key_event('Shift_L', False)
            wait_for(lambda: clipboard.wait_for_text() == 'Green item')
            wait_for(lambda: window_id('Linuxxy') is None)

            # Additional presses continue through the list.
            activate(target_xid)
            for name in ('Shift_L', 'Super_L', 'v'):
                key_event(name, True)
            key_event('v', False)
            wait_for(lambda: window_id('Linuxxy'))
            for _ in range(2):
                key_event('v', True)
                key_event('v', False)
            key_event('Super_L', False)
            key_event('Shift_L', False)
            wait_for(lambda: clipboard.wait_for_text() == 'Blue item')
            wait_for(lambda: window_id('Linuxxy') is None)

            clipboard.set_text(' ', -1)
            clipboard.store()
            activate(target_xid)
            for name in ('Shift_L', 'Super_L', 'v'):
                key_event(name, True)
            key_event('v', False)
            wait_for(lambda: window_id('Linuxxy'))
            for _ in range(3):
                key_event('v', True)
                key_event('v', False)
            screenshot_root('ui_shortcut_cycle_wrap.png')
            key_event('Super_L', False)
            key_event('Shift_L', False)
            wait_for(lambda: clipboard.wait_for_text() == 'Blue item')
            wait_for(lambda: window_id('Linuxxy') is None)
            print('Shortcut opening, cycling, and release selection passed')
        finally:
            target.terminate()
            if app:
                app.terminate()
            target.communicate(timeout=5)
            if app:
                stdout, stderr = app.communicate(timeout=5)
                assert b'Traceback' not in stdout + stderr, (stdout + stderr).decode(errors='replace')[-1200:]
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
