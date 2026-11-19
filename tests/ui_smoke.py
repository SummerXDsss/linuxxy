"""Drive the real X11 application and save screenshots of its visible windows."""
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
from Xlib import X, XK, display
from Xlib.ext import xtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'screenshots'
OUT.mkdir(exist_ok=True)


def wait_for(check, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError('Timed out waiting for UI state')


def window_id(title):
    result = subprocess.run(['wmctrl', '-l'], capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if line.endswith(title):
            return int(line.split()[0], 16)
    return None


def activate(xid):
    subprocess.run(['wmctrl', '-ia', hex(xid)], check=True)
    time.sleep(.2)


def active_window():
    connection = display.Display()
    atom = connection.intern_atom('_NET_ACTIVE_WINDOW')
    prop = connection.screen().root.get_full_property(atom, X.AnyPropertyType)
    result = int(prop.value[0]) if prop and len(prop.value) else None
    connection.close()
    return result


def ensure_keyboard_available():
    connection = display.Display()
    root = connection.screen().root
    status = root.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
    if status == X.GrabSuccess:
        root.ungrab_keyboard(X.CurrentTime)
    connection.close()
    if status != X.GrabSuccess:
        raise RuntimeError('Another desktop application currently holds the keyboard; retry later')


def keys(*names):
    connection = display.Display()
    codes = [connection.keysym_to_keycode(XK.string_to_keysym(name)) for name in names]
    assert all(codes), names
    for code in codes:
        xtest.fake_input(connection, X.KeyPress, code)
    for code in reversed(codes):
        xtest.fake_input(connection, X.KeyRelease, code)
    connection.sync()
    connection.close()
    time.sleep(.15)


def screenshot(xid, name):
    activate(xid)
    time.sleep(.3)
    with tempfile.NamedTemporaryFile(suffix='.xwd') as source:
        subprocess.run(['xwd', '-silent', '-id', hex(xid), '-out', source.name], check=True,
                       capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', source.name,
                        '-frames:v', '1', str(OUT / name)], check=True, capture_output=True)


def main():
    ensure_keyboard_available()
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    original_image = clipboard.wait_for_image() if clipboard.wait_is_image_available() else None
    original_text = clipboard.wait_for_text() if original_image is None else None
    def restore():
        if original_image:
            clipboard.set_image(original_image)
        elif original_text is not None:
            clipboard.set_text(original_text, -1)
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
            target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text() if (temp / 'target-xid').exists() else None))
            activate(target_xid)
            keys('Control_L', 'c')
            def copied():
                database = temp / 'linuxxy/history.sqlite'
                if not database.exists():
                    return False
                with sqlite3.connect(database) as conn:
                    return conn.execute('SELECT 1 FROM entries WHERE text=?',
                                        ('hello linuxxy clipboard',)).fetchone()
            wait_for(copied)
            (temp / 'target-command').write_text('clear')
            wait_for(lambda: (temp / 'target-value').read_text() == '')
            activate(target_xid)
            keys('Shift_L', 'Super_L', 'v')
            popup = wait_for(lambda: window_id('Linuxxy'))
            assert active_window() == popup, 'global shortcut opened popup without focusing it'
            screenshot(popup, 'popup.png')
            keys('Down')
            keys('space')
            preview = wait_for(lambda: window_id('Linuxxy Preview'))
            screenshot(preview, 'preview.png')
            keys('Escape')
            wait_for(lambda: window_id('Linuxxy Preview') is None)
            activate(popup)
            keys('Control_L', 'comma')
            preferences = wait_for(lambda: window_id('Linuxxy Preferences'))
            screenshot(preferences, 'preferences.png')
            keys('Alt_L', 'F4')
            wait_for(lambda: window_id('Linuxxy Preferences') is None)
            activate(popup)
            keys('Return')
            wait_for(lambda: (temp / 'target-value').read_text() == 'hello linuxxy clipboard')
            screenshot(target_xid, 'pasted.png')
            print('UI smoke passed; screenshots saved in', OUT)
        finally:
            target.terminate()
            app.terminate()
            target.communicate(timeout=5)
            app_stdout, app_stderr = app.communicate(timeout=5)
            if app_stdout and b'Traceback' in app_stdout:
                print(app_stdout.decode(errors='replace')[-1000:])
            if app_stderr and b'Traceback' in app_stderr:
                print(app_stderr.decode(errors='replace')[-1000:])

if __name__ == '__main__':
    main()
