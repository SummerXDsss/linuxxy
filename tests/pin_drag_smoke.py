"""Reorder pins with real X11 pointer events and keep click-to-copy working."""

import os
import sys
import tempfile
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk
from Xlib import X, display
from Xlib.ext import xtest

from ui_smoke import activate, screenshot, screenshot_root

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App
from settings import Settings


def pump(seconds=.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def point(row, window):
    x, y = row.translate_coordinates(window, 30, row.get_allocated_height() // 2)
    _ok, origin_x, origin_y = window.get_window().get_origin()
    return origin_x + x, origin_y + y


def move(connection, xy):
    xtest.fake_input(connection, X.MotionNotify, x=xy[0], y=xy[1])
    connection.sync()
    pump(.15)


def click(connection, xy):
    move(connection, xy)
    xtest.fake_input(connection, X.ButtonPress, 1)
    connection.sync()
    pump(.15)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    pump(.35)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        for name in ('Pinned A', 'Pinned B', 'Pinned C'):
            history.add(name)
            entry_id = next(row[0] for row in history.list() if row[1] == name)
            history.pin(entry_id, True)
        history.add('Ordinary item')
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        settings.set('popup_position', 'screen_center')
        app = App()
        connection = display.Display()
        try:
            app.toggle_window()
            pump(.5)
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            activate(xid)
            pins = app.pin_rows.get_children()
            assert [row.value for row in pins] == ['Pinned A', 'Pinned B', 'Pinned C']
            source, target = point(pins[0], app.window), point(pins[2], app.window)
            move(connection, source)
            xtest.fake_input(connection, X.ButtonPress, 1)
            connection.sync()
            pump(.15)
            assert app.pin_drag is not None and not app.pin_drag.active
            move(connection, target)
            pump(.25)
            assert app.pin_drag is not None and app.pin_drag.active
            assert app.pin_drag.target is pins[2]
            screenshot(xid, 'ui_pin_drag_target.png')
            xtest.fake_input(connection, X.ButtonRelease, 1)
            connection.sync()
            pump(.4)
            assert app.pin_drag is None
            assert app.window.get_visible(), 'Dragging chose the item instead of reordering'
            assert [row.value for row in app.pin_rows.get_children()] == [
                'Pinned B', 'Pinned C', 'Pinned A']
            persisted = History(Path(directory) / 'linuxxy/history.sqlite')
            try:
                assert [row[1] for row in persisted.list() if row[2]] == [
                    'Pinned B', 'Pinned C', 'Pinned A']
            finally:
                persisted.close()
            screenshot(xid, 'ui_pin_drag_reordered.png')

            first = app.pin_rows.get_children()[0]
            move(connection, point(first, app.window))
            xtest.fake_input(connection, X.ButtonPress, 3)
            xtest.fake_input(connection, X.ButtonRelease, 3)
            connection.sync()
            pump(.3)
            assert app.context_menu is not None and app.context_menu.get_visible()
            screenshot_root('ui_pin_context_menu.png')
            app.context_menu.popdown()
            pump(.2)
            click(connection, point(first, app.window))
            assert not app.window.get_visible(), 'Clicking a pin did not close the popup'
            assert clipboard.wait_for_text() == 'Pinned B'
            app.toggle_window()
            pump(.5)
            activate(xid)
            ordinary = app.history_rows.get_children()[0]
            click(connection, point(ordinary, app.window))
            assert not app.window.get_visible(), 'Clicking history did not close the popup'
            assert clipboard.wait_for_text() == 'Ordinary item'
            print('Pin drag order, persistence, and mouse copy passed')
        finally:
            connection.close()
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
