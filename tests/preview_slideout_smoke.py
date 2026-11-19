"""Exercise text and image previews on both sides of the real X11 popup."""

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
from Xlib import X, display
from Xlib.ext import xtest

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
        history.add('The full preview follows the selected clipboard item. ' * 8)
        sample = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 160, 80)
        sample.fill(0x4e9aabff)
        ok, png = sample.save_to_bufferv('png', [], [])
        assert ok
        history.add_image(png, source_app='Preview Test')
        history.close()
        settings = Settings()
        settings.set('open_preview_automatically', False)
        settings.set('popup_position', 'screen_center')
        app = App()
        try:
            app.toggle_window()
            pump()
            popup = GdkX11.X11Window.get_xid(app.window.get_window())
            activate(popup)
            pump(.1)
            keys('Control_L', 'space')
            pump(.8)
            assert app.preview is app.preview_pane and app.preview_side == 'right'
            assert app.selected().kind == 'image'
            assert app.window.get_size()[0] > 440
            details = [child.get_text() for child in app.preview_metadata.get_children()
                       if isinstance(child, Gtk.Label)]
            assert 'Application: Preview Test' in details
            assert 'Dimensions: 160×80' in details
            assert 'Copies: 1' in details
            screenshot(popup, 'ui_preview_image_right.png')
            start_preview_width = app.preview_width
            start_content_width = app.content_width
            origin_x, origin_y = app.window.get_position()
            divider_x, divider_y = app.preview_divider.translate_coordinates(app.window, 3, 120)
            root_x, root_y = origin_x + divider_x, origin_y + divider_y
            connection = display.Display()
            xtest.fake_input(connection, X.MotionNotify, x=root_x, y=root_y)
            connection.sync()
            pump(.1)
            xtest.fake_input(connection, X.ButtonPress, 1)
            connection.sync()
            pump(.1)
            xtest.fake_input(connection, X.MotionNotify, x=root_x - 60, y=root_y)
            connection.sync()
            pump(.2)
            xtest.fake_input(connection, X.ButtonRelease, 1)
            connection.sync()
            connection.close()
            pump()
            assert app.preview_width >= start_preview_width + 50
            assert app.content_width <= start_content_width - 50
            assert Settings().get('preview_width') == app.preview_width
            assert Settings().get('popup_width') == app.content_width
            screenshot(popup, 'ui_preview_resized.png')

            keys('Down')
            keys('Down')
            pump()
            assert app.selected().kind == 'text'
            assert app.preview_entry_id == app.selected().entry_id
            text = app.preview_scroll.get_child()
            assert isinstance(text, Gtk.TextView)
            assert 'full preview follows' in text.get_buffer().get_text(
                text.get_buffer().get_start_iter(), text.get_buffer().get_end_iter(), True)
            details = [child.get_text() for child in app.preview_metadata.get_children()
                       if isinstance(child, Gtk.Label)]
            assert any(line.startswith('First copied: ') for line in details)
            assert any(line.startswith('Last copied: ') for line in details)
            screenshot(popup, 'ui_preview_text_right.png')
            image_row = next(row for row in app.rows.get_children() if row.kind == 'image')
            x, y = image_row.translate_coordinates(app.window, 20, 15)
            origin_x, origin_y = app.window.get_position()
            connection = display.Display()
            connection.screen().root.warp_pointer(origin_x + x, origin_y + y)
            connection.sync()
            connection.close()
            pump()
            assert app.selected() is image_row, 'Pointer hover did not select the image'
            assert app.preview_entry_id == image_row.entry_id
            keys('Control_L', 'space')
            pump()
            assert app.preview is None and app.window.get_size()[0] == app.content_width
            app.preview_button.clicked()
            pump()
            assert app.preview is app.preview_pane
            app.preview_button.clicked()
            pump()
            assert app.preview is None and app.window.get_size()[0] == app.content_width
            keys('Escape')
            pump()
            assert not app.window.get_visible()

            settings.set('popup_position', 'cursor')
            app.settings.set('popup_position', 'cursor')
            work = Gdk.Display.get_default().get_primary_monitor().get_workarea()
            connection = display.Display()
            connection.screen().root.warp_pointer(work.x + work.width - 10, work.y + 200)
            connection.sync()
            connection.close()
            app.toggle_window()
            pump()
            activate(popup)
            image_row = next(row for row in app.rows.get_children() if row.kind == 'image')
            app.rows.select_row(image_row)
            image_row.grab_focus()
            pump()
            assert app.selected().kind == 'image'
            keys('Control_L', 'space')
            pump()
            assert app.preview is app.preview_pane and app.preview_side == 'left'
            assert app.preview_entry_id == app.selected().entry_id
            assert app.preview_width == Settings().get('preview_width')
            assert app.content_width == Settings().get('popup_width')
            screenshot(popup, 'ui_preview_image_left.png')
            main_x = app.window.get_position()[0] + app.preview_width + app.preview_divider_width
            keys('Control_L', 'space')
            pump(.8)
            assert app.preview is None
            assert abs(app.window.get_position()[0] - main_x) <= 4, (app.window.get_position(), main_x)
            print('Preview slideout, selection updates, and both placements passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
