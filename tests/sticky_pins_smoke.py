"""Verify fixed pins, scrolling history, and keyboard navigation on X11."""

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
from Xlib import display

from ui_smoke import activate, keys, screenshot

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


def y_in_popup(row, popup):
    return row.translate_coordinates(popup, 0, 0)[1]


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        for index in range(36):
            history.add(f'Clipboard history entry {index:02d}')
        for name in ('Favorite one', 'Favorite two'):
            history.add(name)
            row = next(row for row in history.list() if row[1] == name)
            history.pin(row[0], True)
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        settings.set('popup_position', 'screen_center')
        app = App()
        try:
            app.toggle_window()
            pump(.5)
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            activate(xid)
            pins = app.pin_rows.get_children()
            ordinary = app.history_rows.get_children()
            assert len(pins) == 2 and len(ordinary) == 36
            assert app.rows.get_children()[:2] == pins
            pin_y = [y_in_popup(row, app.window) for row in pins]
            first_history_y = y_in_popup(ordinary[0], app.window)
            adjustment = app.history_scroll.get_vadjustment()
            assert adjustment.get_upper() > adjustment.get_page_size() + 200
            adjustment.set_value(min(320, adjustment.get_upper() - adjustment.get_page_size()))
            pump(.5)
            pins = app.pin_rows.get_children()
            ordinary = app.history_rows.get_children()
            assert [y_in_popup(row, app.window) for row in pins] == pin_y
            assert y_in_popup(ordinary[0], app.window) < first_history_y - 150
            screenshot(xid, 'ui_pins_top_scrolled.png')

            app.rows.select_row(pins[-1])
            pins[-1].grab_focus()
            keys('Down')
            pump(.2)
            assert app.selected() is ordinary[0], 'Down did not cross from pins to history'

            app.settings.set('pins_position', 'bottom')
            app.refresh()
            pump(.5)
            pins = app.pin_rows.get_children()
            ordinary = app.history_rows.get_children()
            assert app.rows.get_children()[-2:] == pins
            assert app.selected().value == ordinary[0].value
            pin_y = [y_in_popup(row, app.window) for row in pins]
            first_history_y = y_in_popup(ordinary[0], app.window)
            adjustment = app.history_scroll.get_vadjustment()
            adjustment.set_value(min(320, adjustment.get_upper() - adjustment.get_page_size()))
            pump(.5)
            pins = app.pin_rows.get_children()
            ordinary = app.history_rows.get_children()
            assert [y_in_popup(row, app.window) for row in pins] == pin_y
            assert y_in_popup(ordinary[0], app.window) < first_history_y - 150
            screenshot(xid, 'ui_pins_bottom_scrolled.png')

            app.rows.select_row(pins[0])
            pins[0].grab_focus()
            footer_x, footer_y = app.footer.translate_coordinates(app.window, 20, 10)
            _ok, origin_x, origin_y = app.window.get_window().get_origin()
            connection = display.Display()
            connection.screen().root.warp_pointer(origin_x + footer_x, origin_y + footer_y)
            connection.sync()
            connection.close()
            pump(.2)
            assert app.selected() is pins[0], 'Pointer over the footer selected an offscreen row'
            keys('Up')
            pump(.2)
            assert app.selected() is ordinary[-1], 'Up did not cross from pins to history'
            assert app.pin_rows.get_selected_row() is None
            app.search.set_text('Favorite one')
            pump(.3)
            assert len(app.pin_rows.get_children()) == 1
            assert not app.history_rows.get_children()
            assert app.pin_container.get_visible()
            app.search.set_text('Clipboard history entry 35')
            pump(.3)
            assert not app.pin_rows.get_children()
            assert len(app.history_rows.get_children()) == 1
            assert not app.pin_container.get_visible()
            app.search.set_text('')
            pump(.3)
            for index in range(20):
                value = f'Extra fixed item {index:02d}'
                app.history.add(value)
                entry_id = next(row[0] for row in app.history.list() if row[1] == value)
                app.history.pin(entry_id, True)
            app.refresh()
            pump(.5)
            assert app.window.get_size()[1] <= app.settings.get('popup_max_height'), app.window.get_size()
            last_pin = app.pin_rows.get_children()[-1]
            app.rows.select_row(last_pin)
            last_pin.grab_focus()
            pump(.3)
            assert app.pin_scroll.get_vadjustment().get_value() > 0
            screenshot(xid, 'ui_many_pins.png')
            print('Fixed pins, both positions, scrolling, and keyboard crossing passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
