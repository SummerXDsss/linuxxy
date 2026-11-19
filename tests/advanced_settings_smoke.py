"""Exercise Advanced settings, pause, clipboard clearing, and pinned quit data."""

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

from ui_smoke import screenshot

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


def descend(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descend(child)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original_image = clipboard.wait_for_image() if clipboard.wait_is_image_available() else None
original_text = clipboard.wait_for_text() if original_image is None else None
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ['XDG_DATA_HOME'] = directory
        os.environ['XDG_CONFIG_HOME'] = directory
        os.environ['XDG_RUNTIME_DIR'] = directory
        os.environ['XDG_SESSION_TYPE'] = 'x11'
        database = Path(directory) / 'linuxxy/history.sqlite'
        history = History(database)
        history.add('Keep this pin')
        history.pin(history.list()[0][0], True)
        history.add('Remove this item')
        history.close()
        app = App()
        try:
            app.show_settings()
            pump()
            notebook = app.preferences.get_child().get_children()[0]
            notebook.set_current_page(3)
            controls = {widget.get_name(): widget for widget in descend(app.preferences)}
            for name in ('linuxxy-pause-monitoring-setting',
                         'linuxxy-clear-on-quit-setting', 'linuxxy-clear-clipboard-setting'):
                controls[name].set_active(True)
            pump()
            screenshot(GdkX11.X11Window.get_xid(app.preferences.get_window()),
                       'ui_advanced.png')
            save = next(widget for widget in descend(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            assert app.paused and Settings().get('monitoring_paused')

            clipboard.set_text('Paused copy', -1)
            clipboard.store()
            app.capture(force=True)
            assert not any(row[1] == 'Paused copy' for row in app.history.list())
            app.toggle_pause()
            assert not app.paused and not Settings().get('monitoring_paused')
            clipboard.set_text('Recorded copy', -1)
            clipboard.store()
            app.capture(force=True)
            assert any(row[1] == 'Recorded copy' for row in app.history.list())

            app.clear()
            pump()
            assert clipboard.wait_for_text() in ('', None)
            assert [row[1] for row in app.history.list()] == ['Keep this pin']
            app.history.add('Remove on quit')
            app.quit()
            reopened = History(database)
            try:
                assert [row[1] for row in reopened.list()] == ['Keep this pin']
            finally:
                reopened.close()
            assert clipboard.wait_for_text() in ('', None)
            print('Advanced settings, pause, clipboard clearing, and pinned quit behavior passed')
        finally:
            if not app.closed:
                app.quit()
finally:
    if original_image is not None:
        clipboard.set_image(original_image)
    elif original_text is not None:
        clipboard.set_text(original_text, -1)
    clipboard.store()
