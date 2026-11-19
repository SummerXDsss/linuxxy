"""Exercise screen choice and last-position reset in the real GTK settings UI."""

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk

from ui_smoke import screenshot, screenshot_root

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


class Monitor:
    def __init__(self, x):
        self.area = SimpleNamespace(x=x, y=0, width=800, height=1200)

    def get_workarea(self):
        return self.area

    def get_geometry(self):
        return self.area


class TwoScreens:
    def __init__(self, real):
        self.real = real
        self.monitors = [Monitor(0), Monitor(800)]

    def get_pointer(self):
        return self.real.get_pointer()

    def get_n_monitors(self):
        return 2

    def get_monitor(self, index):
        return self.monitors[index]

    def get_monitor_at_point(self, x, _y):
        return self.monitors[0 if x < 800 else 1]

    def get_monitor_at_window(self, window):
        _ok, x, _y = window.get_origin()
        return self.get_monitor_at_point(x, 0)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        history.add('Two-screen popup sample')
        history.close()
        settings = Settings()
        settings.set('popup_position', 'screen_center')
        settings.set('popup_last_position', [40, 60])
        settings.set('open_preview_automatically', False)
        try:
            settings.set('popup_screen', True)
            raise AssertionError('Boolean monitor index was accepted')
        except ValueError:
            pass
        app = App()
        try:
            fake = TwoScreens(Gdk.Display.get_default())
            with patch.object(Gdk.Display, 'get_default', return_value=fake):
                assert app.popup_monitor(fake, fake.monitors[0]) is fake.monitors[0]
                app.show_settings()
                pump(.4)
                notebook = next(w for w in descend(app.preferences) if isinstance(w, Gtk.Notebook))
                notebook.set_current_page(2)
                controls = {w.get_name(): w for w in descend(app.preferences)}
                screen = controls['linuxxy-popup-screen-setting']
                assert screen.get_visible() and screen.get_active_id() == '0', (
                    screen.get_visible(), screen.get_active_id(),
                    screen.get_parent().get_visible())
                screen.set_active_id('2')
                pump(.5)
                screenshot(GdkX11.X11Window.get_xid(app.preferences.get_window()),
                           'ui_screen_choice_settings.png')
                save = next(w for w in descend(app.preferences)
                            if isinstance(w, Gtk.Button) and w.get_label() == 'Save')
                save.clicked()
                pump(.2)
                assert Settings().get('popup_screen') == 2
                assert app.popup_monitor(fake, fake.monitors[0]) is fake.monitors[1]
                app.toggle_window()
                pump(.4)
                assert abs(app.window.get_position()[0] - 980) <= 4, app.window.get_position()
                screenshot_root('ui_screen_two_desktop.png')

                app.show_settings()
                pump(.3)
                app.settings.set('popup_last_position', [40, 60])
                notebook = next(w for w in descend(app.preferences) if isinstance(w, Gtk.Notebook))
                notebook.set_current_page(2)
                controls = {w.get_name(): w for w in descend(app.preferences)}
                position = next(w for w in descend(app.preferences)
                                if isinstance(w, Gtk.ComboBoxText) and
                                w.get_active_id() == 'screen_center')
                position.set_active_id('last_position')
                pump(.2)
                reset = controls['linuxxy-reset-position-setting']
                assert reset.get_visible()
                save = next(w for w in descend(app.preferences)
                            if isinstance(w, Gtk.Button) and w.get_label() == 'Save')
                save.clicked()
                pump(.2)
                app.toggle_window()
                pump(.4)
                assert abs(app.window.get_position()[0] - 840) <= 4, app.window.get_position()
                assert abs(app.window.get_position()[1] - 60) <= 4, app.window.get_position()

                app.show_settings()
                pump(.3)
                notebook = next(w for w in descend(app.preferences) if isinstance(w, Gtk.Notebook))
                notebook.set_current_page(2)
                controls = {w.get_name(): w for w in descend(app.preferences)}
                reset = controls['linuxxy-reset-position-setting']
                assert reset.get_visible()
                pump(.4)
                screenshot(GdkX11.X11Window.get_xid(app.preferences.get_window()),
                           'ui_reset_last_position_setting.png')
                reset.clicked()
                save = next(w for w in descend(app.preferences)
                            if isinstance(w, Gtk.Button) and w.get_label() == 'Save')
                save.clicked()
                pump(.2)
                assert Settings().get('popup_last_position') is None
                app.toggle_window()
                pump(.4)
                assert abs(app.window.get_position()[0] - 980) <= 4, app.window.get_position()
                assert abs(app.window.get_position()[1] - 240) <= 4, app.window.get_position()
                screenshot_root('ui_reset_position_desktop.png')
            print('Screen choice, relative last position, and reset passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
