"""Open the real editor, save an item, and inspect the resulting popup."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App

OUT = ROOT / 'screenshots'
OUT.mkdir(exist_ok=True)


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


def screenshot(window, name, directory):
    xid = GdkX11.X11Window.get_xid(window.get_window())
    raw = Path(directory) / 'shot.xwd'
    subprocess.run(['xwd', '-silent', '-id', hex(xid), '-out', str(raw)],
                   check=True, capture_output=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw),
                    '-frames:v', '1', str(OUT / name)], check=True, capture_output=True)


with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_DATA_HOME'] = directory
    os.environ['XDG_CONFIG_HOME'] = directory
    os.environ['XDG_RUNTIME_DIR'] = directory
    history = History(Path(directory) / 'linuxxy/history.sqlite')
    history.add('original paste text')
    entry_id = history.list()[0][0]
    history.pin(entry_id, True)
    history.close()

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text('', -1)
    clipboard.store()
    app = App()
    app.toggle_window()
    result = []

    def save_editor():
        editor = next(window for window in Gtk.Window.list_toplevels()
                      if window.get_title() == 'Edit clipboard item')
        widgets = list(descendants(editor))
        alias = next(widget for widget in widgets if isinstance(widget, Gtk.Entry))
        content = next(widget for widget in widgets if isinstance(widget, Gtk.TextView))
        pin = next(widget for widget in widgets if isinstance(widget, Gtk.ComboBoxText))
        save_button = next(widget for widget in widgets
                           if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
        assert not save_button.get_sensitive()
        alias.set_text('Daily note')
        content.get_buffer().set_text('updated paste text')
        pin.set_active_id('x')
        assert save_button.get_sensitive()
        def capture_and_submit():
            screenshot(editor, 'ui_edit_item.png', directory)
            editor.response(Gtk.ResponseType.OK)
            return False
        GLib.timeout_add(120, capture_and_submit)
        return False

    def capture_result():
        item = app.history.get(entry_id)
        assert (item['alias'], item['text'], item['pin_key']) == (
            'Daily note', 'updated paste text', 'x'
        ), item
        row = next(row for row in app.rows.get_children() if row.entry_id == entry_id)
        assert row.display_title == 'Daily note' and row.pin_key == 'x'
        screenshot(app.window, 'ui_edited_item.png', directory)
        app.choose(row, paste=False)
        assert clipboard.wait_for_text() == 'updated paste text'
        result.append(True)
        app.quit()
        return False

    def open_editor():
        row = next(row for row in app.rows.get_children() if row.entry_id == entry_id)
        app.rows.select_row(row)
        GLib.timeout_add(120, save_editor)
        app.edit_selected()
        GLib.timeout_add(140, capture_result)
        return False

    GLib.timeout_add(150, open_editor)
    def timed_out():
        print('Editor UI timed out', file=sys.stderr, flush=True)
        os._exit(2)
    GLib.timeout_add(5000, timed_out)
    Gtk.main()
    assert result, 'Editor interaction did not finish'
    print('Editor UI passed; screenshots saved')
