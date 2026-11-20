"""Move the popup by its background with real X11 pointer events."""

import os
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk
from Xlib import X, display
from Xlib.ext import xtest

from ui_smoke import activate, screenshot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App
from settings import Settings


def pump(seconds=.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def origin(window):
    return window.get_window().get_origin()[-2:]


def drag(connection, start, end):
    xtest.fake_input(connection, X.MotionNotify, x=start[0], y=start[1])
    connection.sync()
    pump(.1)
    xtest.fake_input(connection, X.ButtonPress, 1)
    connection.sync()
    pump(.15)
    xtest.fake_input(connection, X.MotionNotify, x=end[0], y=end[1])
    connection.sync()
    pump(.3)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    pump(.3)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        history.add('A window to move')
        history.close()
        settings = Settings()
        settings.set('popup_position', 'last_position')
        settings.set('open_preview_automatically', False)
        app = App()
        connection = display.Display()
        try:
            app.toggle_window()
            pump(.5)
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            activate(xid)
            before = origin(app.window)
            x, y = app.title_handle.translate_coordinates(
                app.window, 10, app.title_handle.get_allocated_height() // 2)
            start = before[0] + x, before[1] + y
            drag(connection, start, (start[0] + 130, start[1] + 80))
            after = origin(app.window)
            assert after[0] - before[0] >= 60 and after[1] - before[1] >= 40, (
                'Title drag did not move the popup', before, after)
            strip_start = after[0] + app.window.get_allocated_width() // 2, after[1] + 4
            drag(connection, strip_start, (strip_start[0] + 110, strip_start[1] + 70))
            after_strip = origin(app.window)
            assert after_strip[0] - after[0] >= 60 and after_strip[1] - after[1] >= 40, (
                'Empty top edge did not move the popup', after, after_strip)
            search_x, search_y = app.search.translate_coordinates(
                app.window, app.search.get_allocated_width() // 2,
                app.search.get_allocated_height() // 2)
            search_start = after_strip[0] + search_x, after_strip[1] + search_y
            drag(connection, search_start, (search_start[0] + 70, search_start[1] + 50))
            assert origin(app.window) == after_strip, 'Dragging in search moved the popup'
            screenshot(xid, 'ui_popup_moved.png')
            app.show_preview()
            pump(.4)
            before_preview_drag = origin(app.window)
            heading_x, heading_y = app.preview_heading.translate_coordinates(
                app.window, 25, app.preview_heading.get_allocated_height() // 2)
            heading_start = (before_preview_drag[0] + heading_x,
                             before_preview_drag[1] + heading_y)
            drag(connection, heading_start,
                 (heading_start[0] - 90, heading_start[1] + 45))
            after_preview_drag = origin(app.window)
            assert after_preview_drag[0] - before_preview_drag[0] <= -40, (
                'Preview background did not move the popup', before_preview_drag,
                after_preview_drag)
            app.cancel_preview()
            pump(.2)
            final_position = origin(app.window)
            app.hide_window()
            assert Settings().get('popup_last_position') == list(final_position)
            app.toggle_window()
            pump(.5)
            assert origin(app.window) == final_position
            print('Title, empty-area and preview drag, search interaction, and saved position passed')
        finally:
            connection.close()
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
