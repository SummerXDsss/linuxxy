"""Record popup shortcuts in settings and use them with real X11 keys."""

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

from ui_smoke import activate, keys, screenshot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App
from settings import Settings


def pump(seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


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
        history.add('Shortcut sample item')
        history.close()
        app = App()
        try:
            app.show_settings()
            pump()
            entries = {entry.get_text(): entry for entry in descendants(app.preferences)
                       if isinstance(entry, Gtk.Entry)}
            for old, new, names in (
                ('Alt+P', 'Ctrl+Shift+P', ('Control_L', 'Shift_L', 'p')),
                ('Alt+Delete', 'Ctrl+Shift+Delete', ('Control_L', 'Shift_L', 'Delete')),
                ('Ctrl+Space', 'Ctrl+F3', ('Control_L', 'F3')),
            ):
                entry = entries[old]
                entry.grab_focus()
                pump(.1)
                keys(*names)
                pump(.15)
                assert entry.get_text() == new, (old, entry.get_text())
            screenshot(GdkX11.X11Window.get_xid(app.preferences.get_window()),
                       'ui_action_shortcuts.png')
            save = next(widget for widget in descendants(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            saved = Settings()
            assert [saved.get(key) for key in ('pin_shortcut', 'delete_shortcut',
                                               'preview_shortcut')] == [
                'Ctrl+Shift+P', 'Ctrl+Shift+Delete', 'Ctrl+F3']

            app.toggle_window()
            pump()
            popup = GdkX11.X11Window.get_xid(app.window.get_window())
            activate(popup)
            pump(.1)
            keys('Alt_L', 'p')
            pump()
            assert app.history.list()[0][2] == 0, 'Old pin shortcut remained active'
            keys('Control_L', 'Shift_L', 'p')
            pump()
            assert app.history.list()[0][2] == 1, 'Recorded pin shortcut did not pin item'
            keys('Control_L', 'F3')
            pump()
            assert app.preview and app.preview.get_visible(), 'Recorded preview shortcut failed'
            activate(GdkX11.X11Window.get_xid(app.preview.get_window()))
            keys('Control_L', 'F3')
            pump()
            assert app.preview is None, 'Recorded preview shortcut did not close preview'
            activate(popup)
            pump(.1)
            keys('Control_L', 'Shift_L', 'Delete')
            pump()
            assert not app.history.list(), 'Recorded delete shortcut did not delete item'
            app.history.add('New sample item')
            app.refresh()
            app.show_settings()
            pump()
            pin_entry = next(entry for entry in descendants(app.preferences)
                             if isinstance(entry, Gtk.Entry) and entry.get_text() == 'Ctrl+Shift+P')
            clear = next(widget for widget in pin_entry.get_parent().get_children()
                         if isinstance(widget, Gtk.Button))
            clear.clicked()
            assert pin_entry.get_text() == ''
            save = next(widget for widget in descendants(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            assert Settings().get('pin_shortcut') == ''
            app.toggle_window()
            pump()
            activate(popup)
            pump(.1)
            keys('Control_L', 'Shift_L', 'p')
            pump()
            assert app.history.list()[0][2] == 0, 'Cleared shortcut remained active'
            print('Action shortcut recording, persistence, and UI actions passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
