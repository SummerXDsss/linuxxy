"""Exercise tray appearance controls and recent-copy updates in a real GTK session."""

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
        history.add('Earlier copy')
        history.add('Most recent sample')
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        app = App()
        try:
            assert app.tray.get_property('visible')
            app.show_settings()
            pump()
            notebook = app.preferences.get_child().get_children()[0]
            notebook.set_current_page(2)
            scroll = notebook.get_nth_page(2)
            adjustment = scroll.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            controls = {widget.get_name(): widget for widget in descend(app.preferences)}
            controls['linuxxy-show-tray-setting'].set_active(False)
            controls['linuxxy-tray-icon-setting'].set_active_id('scissors')
            controls['linuxxy-tray-recent-setting'].set_active(True)
            pump()
            screenshot(GdkX11.X11Window.get_xid(app.preferences.get_window()),
                       'ui_tray_settings.png')
            save = next(widget for widget in descend(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            assert not app.tray.get_property('visible')
            assert app.tray.get_property('icon-name') == 'edit-cut'
            assert app.tray.get_property('title') == 'Most recent sample'
            assert 'Most recent sample' in app.tray.get_property('tooltip-text')
            assert Settings().get('tray_icon') == 'scissors'

            app.toggle_window()
            pump()
            assert app.window.get_visible(), 'Popup unavailable with hidden tray icon'
            app.hide_window()
            app.show_settings()
            pump()
            controls = {widget.get_name(): widget for widget in descend(app.preferences)}
            controls['linuxxy-show-tray-setting'].set_active(True)
            controls['linuxxy-tray-icon-setting'].set_active_id('paperclip')
            save = next(widget for widget in descend(app.preferences)
                        if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
            save.clicked()
            pump()
            assert app.tray.get_property('visible')
            assert app.tray.get_property('icon-name') == 'mail-attachment-symbolic'

            clipboard.set_text('A newly copied sentence', -1)
            clipboard.store()
            app.capture(force=True)
            assert app.tray.get_property('title') == 'A newly copied sentence'
            latest_id = next(row[0] for row in app.history.list() if row[1] == 'A newly copied sentence')
            app.history.pin(latest_id, True)
            app.refresh()
            assert app.tray.get_property('title') == 'Most recent sample'
            app.toggle_pause()
            assert '(paused)' in app.tray.get_property('tooltip-text')
            print('Tray icon visibility, style, recent copy, and hidden-tray popup passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
