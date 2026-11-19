"""Change the popup size in Preferences and measure the real X11 window."""

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


def pump(seconds=.3):
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
        for index in range(30):
            history.add(f'Clipboard item {index:02d}')
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        settings.set('popup_position', 'screen_center')
        app = App()
        try:
            app.toggle_window()
            pump()
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            assert app.window.get_size()[0] == 440
            assert 470 < app.window.get_size()[1] <= 800
            app.show_settings()
            pump()
            controls = {widget.get_name(): widget for widget in descend(app.preferences)}
            controls['linuxxy-popup-width-setting'].set_value(520)
            controls['linuxxy-popup-height-setting'].set_value(500)
            save = next(widget for widget in descend(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            assert Settings().get('popup_width') == 520
            assert Settings().get('popup_max_height') == 500
            app.toggle_window()
            pump()
            assert app.window.get_size() == (520, 500), app.window.get_size()
            screenshot(xid, 'ui_large_popup.png')
            print('Popup width, height limit, and saved Appearance controls passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
