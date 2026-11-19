"""Measure the popup at real X11 locations for each position setting."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from Xlib import X, display
from Xlib.ext import xtest
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk
from ui_smoke import activate, keys, screenshot_root, wait_for, window_id

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from settings import Settings


def bounds(xid):
    connection = display.Display()
    window = connection.create_resource_object('window', xid)
    geometry = window.get_geometry()
    point = connection.screen().root.translate_coords(window, 0, 0)
    connection.close()
    return point.x, point.y, geometry.width, geometry.height


with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    legacy = temp / 'legacy-settings.json'
    legacy.write_text('{"popup_at_cursor": false}')
    assert Settings(legacy).get('popup_position') == 'screen_center'
    legacy.write_text('{"popup_at_cursor": true}')
    assert Settings(legacy).get('popup_position') == 'cursor'
    env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
               XDG_RUNTIME_DIR=directory, LINUXXY_TEST_XID=str(temp / 'target-xid'),
               LINUXXY_TEST_VALUE=str(temp / 'target-value'),
               LINUXXY_TEST_COMMAND=str(temp / 'target-command'))
    history = History(temp / 'linuxxy/history.sqlite')
    history.add('Popup position sample')
    history.close()
    target = subprocess.Popen([sys.executable, str(ROOT / 'tests/paste_target.py')],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        target_xid = int(wait_for(lambda: (temp / 'target-xid').read_text()
                                  if (temp / 'target-xid').exists() else None))
        subprocess.run(['wmctrl', '-ir', hex(target_xid), '-e', '0,100,100,440,100'], check=True)
        settings = Settings(temp / 'linuxxy/settings.json')
        settings.set('open_preview_automatically', False)
        settings.set('popup_last_position', [40, 60])
        gdk_display = Gdk.Display.get_default()
        work = gdk_display.get_primary_monitor().get_workarea()
        pointer = (work.x + work.width - 30, work.y + work.height - 30)

        saved_position = (40, 60)
        for mode in ('cursor', 'status_icon', 'active_window', 'screen_center',
                     'last_position', 'last_position_reopen'):
            settings = Settings(temp / 'linuxxy/settings.json')
            settings.set('popup_position', mode.removesuffix('_reopen'))
            if mode == 'last_position':
                settings.set('popup_last_position', [40, 60])
            app = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                time.sleep(.5)
                assert app.poll() is None, f'Linuxxy did not start for {mode}'
                activate(target_xid)
                connection = display.Display()
                connection.screen().root.warp_pointer(*pointer)
                connection.sync()
                connection.close()
                keys('Shift_L', 'Super_L', 'v')
                popup = wait_for(lambda: window_id('Linuxxy'))
                time.sleep(.2)
                x, y, width, height = bounds(popup)
                if mode in ('cursor', 'status_icon'):
                    expected = (min(pointer[0], work.x + work.width - width),
                                min(pointer[1], work.y + work.height - height))
                elif mode == 'active_window':
                    tx, ty, tw, th = bounds(target_xid)
                    expected = (max(0, (tx + tw // 2) - width // 2),
                                max(0, (ty + th // 2) - height // 2))
                elif mode == 'screen_center':
                    expected = (work.x + (work.width - width) // 2,
                                work.y + (work.height - height) // 2)
                else:
                    expected = saved_position
                assert abs(x - expected[0]) <= 4 and abs(y - expected[1]) <= 4, (
                    mode, (x, y), expected, (width, height))
                screenshot_root(f'ui_position_{mode}.png')
                print(mode, (x, y), expected)
                if mode == 'last_position':
                    connection = display.Display()
                    xtest.fake_input(connection, X.MotionNotify, x=x + 20, y=y + 20)
                    xtest.fake_input(connection, X.ButtonPress, 1)
                    connection.sync()
                    time.sleep(.1)
                    xtest.fake_input(connection, X.MotionNotify, x=x + 250, y=y + 170)
                    connection.sync()
                    time.sleep(.2)
                    xtest.fake_input(connection, X.ButtonRelease, 1)
                    connection.sync()
                    connection.close()
                    time.sleep(.2)
                    moved = bounds(popup)
                    assert moved[:2] != (x, y), ('title drag did not move popup', moved)
                    keys('Escape')
                    wait_for(lambda: window_id('Linuxxy') is None)
                    saved_position = tuple(Settings(temp / 'linuxxy/settings.json').get(
                        'popup_last_position'))
                    assert saved_position == moved[:2], (saved_position, moved)
            finally:
                app.terminate()
                stdout, stderr = app.communicate(timeout=5)
                assert b'Traceback' not in stdout + stderr, (stdout + stderr).decode(errors='replace')[-1200:]
    finally:
        target.terminate()
        target.communicate(timeout=5)
