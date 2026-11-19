"""Copy many texts from another X11 process and inspect the glass popup."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cairo
import gi

gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk

from ui_smoke import activate, keys, screenshot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linuxxy import App
from settings import Settings

SOURCE = r'''
import sys
import gi
gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk
clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def receive(source, condition):
    line = source.readline()
    if not line:
        Gtk.main_quit()
        return False
    clipboard.set_text(line.rstrip('\n'), -1)
    sys.stdout.write('copied\n')
    sys.stdout.flush()
    return True
GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, receive)
Gtk.main()
'''

COPIES = (
    'First idea — 早上待办',
    'https://example.com/docs/linuxxy',
    'Meeting notes: release checklist',
    'Code: git status --short',
    'A short snippet',
    'Invoice #4821 | paid',
    'Color #7A91FF',
    'A longer paragraph that should be shortened in the history row',
    'Remember this useful command',
    '测试中文剪贴板内容',
    'Second to last copy',
    'Most recent copy ✓',
)


def pump(seconds=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def wait_for_count(app, count):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        pump(.04)
        if len(app.history.list()) == count:
            return
    raise AssertionError(f'Expected {count} copies, got {len(app.history.list())}')


def draw_background(widget, cr):
    width, height = widget.get_allocated_width(), widget.get_allocated_height()
    base = cairo.LinearGradient(0, 0, width, height)
    base.add_color_stop_rgb(0, .08, .17, .35)
    base.add_color_stop_rgb(.55, .27, .42, .75)
    base.add_color_stop_rgb(1, .72, .47, .57)
    cr.set_source(base)
    cr.paint()
    for x, y, radius, color in ((width * .26, height * .23, 360, (.42, .77, 1)),
                                (width * .73, height * .68, 420, (1, .56, .45))):
        glow = cairo.RadialGradient(x, y, 0, x, y, radius)
        glow.add_color_stop_rgba(0, *color, .85)
        glow.add_color_stop_rgba(1, *color, 0)
        cr.set_source(glow)
        cr.paint()
    return True


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        settings = Settings()
        settings.set('popup_position', 'screen_center')
        settings.set('popup_max_height', 500)
        settings.set('check_interval_ms', 100)
        settings.set('open_preview_automatically', False)
        root = Gdk.get_default_root_window()
        background = Gtk.Window(title='Many copies background')
        background.set_decorated(False)
        background.set_default_size(root.get_width(), root.get_height())
        background.move(0, 0)
        background.connect('draw', draw_background)
        background.show_all()
        pump(.4)
        app = App()
        source = subprocess.Popen([sys.executable, '-u', '-c', SOURCE],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, env=os.environ.copy())
        try:
            for count, value in enumerate(COPIES, 1):
                source.stdin.write(value + '\n')
                source.stdin.flush()
                assert source.stdout.readline().strip() == 'copied'
                wait_for_count(app, count)
            assert [entry[1] for entry in app.history.list()] == list(reversed(COPIES))
            app.toggle_window()
            pump(.6)
            assert app.window.backdrop is not None
            assert app.window.get_allocated_height() <= 500
            assert len(app.rows.get_children()) == len(COPIES)
            assert app.selected().value == COPIES[-1]
            assert app.selected().content.get_style_context().has_class('linuxxy-selected')
            xid = GdkX11.X11Window.get_xid(app.window.get_window())
            screenshot(xid, 'ui_glass_many_copies.png')
            activate(xid)
            for _ in COPIES:
                keys('Down')
            pump(.4)
            assert app.selected().value == COPIES[0]
            assert app.history_scroll.get_vadjustment().get_value() > 0
            screenshot(xid, 'ui_glass_many_copies_scrolled.png')
            print('Twelve external X11 copies, history order, popup height, and scrolling passed')
        finally:
            source.stdin.close()
            source.wait(timeout=3)
            app.quit()
            background.destroy()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
