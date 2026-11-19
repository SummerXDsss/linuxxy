"""Render glass over a patterned X11 window and inspect both system color schemes."""

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


def draw_pattern(widget, cr):
    for y in range(0, widget.get_allocated_height(), 96):
        for x in range(0, widget.get_allocated_width(), 96):
            cr.set_source_rgb(*((.22, .42, .88) if (x // 96 + y // 96) % 2 else
                                (.97, .66, .28)))
            cr.rectangle(x, y, 96, 96)
            cr.fill()
    return True


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
        background = Gtk.Window(title='Glass background sample')
        background.set_decorated(False)
        root = Gdk.get_default_root_window()
        background.set_default_size(root.get_width(), root.get_height())
        background.move(0, 0)
        background.connect('draw', draw_pattern)
        background.show_all()
        pump(.5)
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        for text in ('Glass preview', 'Pinned example', 'Search your clipboard'):
            history.add(text)
        history.pin(next(row[0] for row in history.list() if row[1] == 'Pinned example'), True)
        history.close()
        settings = Settings()
        assert settings.get('popup_theme') == 'glass'
        settings.set('popup_position', 'screen_center')
        settings.set('open_preview_automatically', False)
        app = App()
        try:
            app.toggle_window()
            pump(.6)
            assert app.window.backdrop is not None
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            screenshot(xid, 'ui_glass_light.png')
            app.show_preview()
            pump(.6)
            screenshot(xid, 'ui_glass_preview.png')
            app.cancel_preview()
            gtk_settings.set_property('gtk-application-prefer-dark-theme', True)
            pump(.6)
            assert app.window.glass_dark
            screenshot(xid, 'ui_glass_dark.png')
            print('Glass backdrop, preview, and live light/dark appearance passed')
        finally:
            app.quit()
            background.destroy()
finally:
    gtk_settings.set_property('gtk-theme-name', original_theme)
    gtk_settings.set_property('gtk-application-prefer-dark-theme', original_dark)
    if original_clipboard is not None:
        clipboard.set_text(original_clipboard, -1)
        clipboard.store()
