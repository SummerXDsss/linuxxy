"""Switch the real popup between system, light, and dark appearance."""

import os
import sys
import tempfile
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk

from ui_smoke import screenshot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App
from settings import Settings


def pump(seconds=.35):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def descend(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descend(child)


def background_brightness(name):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(ROOT / 'screenshots' / name))
    x, y = 3, 45
    offset = y * pixbuf.get_rowstride() + x * pixbuf.get_n_channels()
    return sum(pixbuf.get_pixels()[offset:offset + 3]) / 3


def choose_theme(app, name):
    app.show_settings()
    pump()
    control = next(w for w in descend(app.preferences)
                   if w.get_name() == 'linuxxy-popup-theme-setting')
    control.set_active_id(name)
    save = next(w for w in descend(app.preferences)
                if isinstance(w, Gtk.Button) and w.get_label() == 'Save')
    save.clicked()
    pump()
    assert Settings().get('popup_theme') == name
    app.toggle_window()
    pump(.5)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original_clipboard = clipboard.wait_for_text()
gtk_settings = Gtk.Settings.get_default()
original_theme = gtk_settings.get_property('gtk-theme-name')
original_dark = gtk_settings.get_property('gtk-application-prefer-dark-theme')
clipboard.set_text(' ', -1)
clipboard.store()
try:
    gtk_settings.set_property('gtk-theme-name', 'Adwaita')
    gtk_settings.set_property('gtk-application-prefer-dark-theme', False)
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        history.add('Theme sample first')
        history.add('Theme sample second')
        history.pin(history.list()[0][0], True)
        history.close()
        settings = Settings()
        settings.set('popup_theme', 'system')
        settings.set('popup_position', 'screen_center')
        settings.set('open_preview_automatically', False)
        app = App()
        try:
            app.toggle_window()
            pump(.5)
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            screenshot(xid, 'ui_theme_system_light.png')
            assert background_brightness('ui_theme_system_light.png') > 180

            choose_theme(app, 'dark')
            screenshot(xid, 'ui_theme_dark.png')
            assert background_brightness('ui_theme_dark.png') < 100
            app.show_preview()
            pump(.8)
            assert app.preview is app.preview_pane
            screenshot(xid, 'ui_theme_dark_preview.png')
            app.cancel_preview()
            pump(.5)

            choose_theme(app, 'light')
            screenshot(xid, 'ui_theme_light.png')
            assert background_brightness('ui_theme_light.png') > 180

            choose_theme(app, 'system')
            gtk_settings.set_property('gtk-application-prefer-dark-theme', True)
            pump(.7)
            screenshot(xid, 'ui_theme_system_dark.png')
            assert background_brightness('ui_theme_system_dark.png') < 100
            print('System, light, dark, persistence, and live theme changes passed')
        finally:
            app.quit()
finally:
    gtk_settings.set_property('gtk-theme-name', original_theme)
    gtk_settings.set_property('gtk-application-prefer-dark-theme', original_dark)
    if original_clipboard is not None:
        clipboard.set_text(original_clipboard, -1)
        clipboard.store()
