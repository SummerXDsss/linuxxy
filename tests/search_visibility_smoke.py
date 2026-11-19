"""Search with a field that appears while typing or stays hidden."""

import atexit
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

from ui_smoke import activate, keys, screenshot, wait_for, window_id

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from settings import Settings


def main():
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    original_image = clipboard.wait_for_image() if clipboard.wait_is_image_available() else None
    original_text = clipboard.wait_for_text() if original_image is None else None
    def restore():
        if original_image:
            clipboard.set_image(original_image)
        elif original_text is not None:
            clipboard.set_text(original_text, -1)
        if original_image or original_text is not None:
            clipboard.store()
    atexit.register(restore)

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                   XDG_RUNTIME_DIR=directory,
                   LINUXXY_TEST_XID=str(temp / 'target-xid'),
                   LINUXXY_TEST_VALUE=str(temp / 'target-value'),
                   LINUXXY_TEST_COMMAND=str(temp / 'target-command'))
        history = History(temp / 'linuxxy/history.sqlite')
        history.add('Copper item')
        history.add('Violet item')
        history.add('Orange item')
        history.close()
        settings = Settings(temp / 'linuxxy/settings.json')
        settings.set('search_visibility', 'during_search')
        target = subprocess.Popen([sys.executable, str(ROOT / 'tests/paste_target.py')],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text()
                                      if (temp / 'target-xid').exists() else None))

            def run_app(mode):
                app = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    time.sleep(.7)
                    assert app.poll() is None, 'Linuxxy exited before opening'
                    activate(target_xid)
                    keys('Shift_L', 'Super_L', 'v')
                    popup = wait_for(lambda: window_id('Linuxxy'))
                    screenshot(popup, 'ui_search_hidden.png' if mode == 'during' else 'ui_search_off.png')
                    keys('v' if mode == 'during' else 'c')
                    if mode == 'during':
                        keys('i')
                        keys('o')
                    screenshot(popup, 'ui_search_typing.png' if mode == 'during' else 'ui_search_off_typing.png')
                    if mode == 'during':
                        keys('Control_L', 'a')
                        keys('BackSpace')
                        keys('v')
                        keys('i')
                        keys('o')
                    else:
                        keys('BackSpace')
                        screenshot(popup, 'ui_search_off_cleared.png')
                        keys('c')
                    keys('Return')
                    expected = 'Violet item' if mode == 'during' else 'Copper item'
                    wait_for(lambda: clipboard.wait_for_text() == expected)
                    wait_for(lambda: window_id('Linuxxy') is None)
                finally:
                    app.terminate()
                    stdout, stderr = app.communicate(timeout=5)
                    if b'Traceback' in stdout or b'Traceback' in stderr:
                        raise AssertionError((stdout + stderr).decode(errors='replace')[-1200:])

            run_app('during')
            settings.set('show_search_field', False)
            run_app('off')
            print('Search visibility and keyboard search passed; screenshots saved')
        finally:
            target.terminate()
            target.communicate(timeout=5)


if __name__ == '__main__':
    main()
