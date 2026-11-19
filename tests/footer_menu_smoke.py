"""Use the popup's menu-style footer with real X11 pointer and keyboard events."""

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

from ui_smoke import activate, keys, screenshot

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


def click(app, widget, popup):
    activate(popup)
    x, y = widget.translate_coordinates(app.window, 25, 12)
    origin_x, origin_y = app.window.get_position()
    connection = display.Display()
    xtest.fake_input(connection, X.MotionNotify, x=origin_x + x, y=origin_y + y)
    xtest.fake_input(connection, X.ButtonPress, 1)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    connection.close()
    pump()


def confirm_clear(name, remember=False):
    dialog = next(window for window in Gtk.Window.list_toplevels()
                  if isinstance(window, Gtk.MessageDialog) and window.get_visible())
    pump(.5)
    xid = GdkX11.X11Window.get_xid(dialog.get_window())
    screenshot(xid, name)
    if remember:
        checkbox = next(widget for widget in dialog.get_message_area().get_children()
                        if isinstance(widget, Gtk.CheckButton))
        checkbox.set_active(True)
    button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    x, y = button.translate_coordinates(dialog, 20, 12)
    origin_x, origin_y = dialog.get_window().get_origin()[-2:]
    connection = display.Display()
    xtest.fake_input(connection, X.MotionNotify, x=origin_x + x, y=origin_y + y)
    xtest.fake_input(connection, X.ButtonPress, 1)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    connection.close()
    pump()


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ['XDG_DATA_HOME'] = directory
        os.environ['XDG_CONFIG_HOME'] = directory
        os.environ['XDG_RUNTIME_DIR'] = directory
        os.environ['XDG_SESSION_TYPE'] = 'x11'
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        history.add('Pinned note')
        history.pin(history.list()[0][0], True)
        history.add('Disposable note')
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        settings.set('popup_position', 'screen_center')
        app = App()
        try:
            app.toggle_window()
            pump(.8)
            popup = GdkX11.X11Window.get_xid(app.window.get_window())
            screenshot(popup, 'ui_footer_menu.png')
            click(app, app.about_button, popup)
            assert app.about and app.about.get_visible()
            screenshot(GdkX11.X11Window.get_xid(app.about.get_window()), 'ui_about.png')
            keys('Escape')
            pump()
            assert app.about is None

            click(app, app.clear_button, popup)
            pending = next(window for window in Gtk.Window.list_toplevels()
                           if isinstance(window, Gtk.MessageDialog) and window.get_visible())
            pending.response(Gtk.ResponseType.CANCEL)
            pump()
            assert any(row[1] == 'Disposable note' for row in app.history.list())
            click(app, app.clear_button, popup)
            confirm_clear('ui_clear_confirmation.png')
            assert [row[1] for row in app.history.list()] == ['Pinned note']
            assert not app.window.get_visible()
            app.toggle_window()
            pump()
            click(app, app.preferences_button, popup)
            assert app.preferences and app.preferences.get_visible()
            app.preferences.destroy()
            pump()
            app.show_about()
            pump()
            assert app.about and app.about.get_mapped(), 'About did not open from a hidden popup'
            app.about.response(Gtk.ResponseType.CLOSE)
            pump()
            app.toggle_window()
            pump()
            activate(popup)
            keys('Control_L', 'Alt_L', 'Shift_L', 'Delete')
            pump()
            confirm_clear('ui_clear_all_confirmation.png', remember=True)
            assert not app.history.list()
            assert not app.window.get_visible()
            assert Settings().get('suppress_clear_confirmation')
            app.history.add('Clear without another prompt')
            app.confirm_clear()
            assert not app.history.list()
            assert not any(isinstance(window, Gtk.MessageDialog) and window.get_visible()
                           for window in Gtk.Window.list_toplevels())
            app.history.add('Quit shortcut item')
            app.toggle_window()
            pump()
            activate(popup)
            keys('Control_L', 'q')
            pump()
            assert app.closed
            print('Footer rows, About, Clear, Preferences, and Ctrl+Q passed')
        finally:
            if not app.closed:
                app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
