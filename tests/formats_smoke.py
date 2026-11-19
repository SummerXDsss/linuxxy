"""Check HTML and file URI clipboard round trips between separate X11 clients."""
import os
import hashlib
import pickle
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from Xlib import display

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import History
from linuxxy import App


def wait_for(check, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError('Timed out waiting for clipboard data')


def query(code):
    process = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    end = time.monotonic() + 4
    context = GLib.MainContext.default()
    while process.poll() is None and time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(.01)
    if process.poll() is None:
        process.kill()
    out, err = process.communicate()
    assert process.returncode == 0, err
    return out.strip()


def check(kind, formats, expected_data, query_code, expected_output=None):
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                   XDG_RUNTIME_DIR=directory, PYTHONPATH=str(ROOT))
        payload = Path(directory) / 'formats.pickle'
        with payload.open('wb') as output:
            pickle.dump(formats, output)
        source_code = (
            'import pickle;from x11_clipboard import X11Clipboard;'
            'from gi.repository import GLib;'
            f"owner=X11Clipboard();owner.set(pickle.load(open({str(payload)!r},'rb')));"
            "print('ready',flush=True);GLib.MainLoop().run()"
        )
        source = subprocess.Popen([sys.executable, '-u', '-c', source_code], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        app_process = None
        try:
            assert source.stdout.readline().strip() == 'ready'
            app_process = subprocess.Popen([sys.executable, str(ROOT / 'linuxxy.py')], env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            db = Path(directory) / 'linuxxy/history.sqlite'
            def captured():
                if not db.exists():
                    return None
                with sqlite3.connect(db) as conn:
                    try:
                        return conn.execute('SELECT text,data FROM entries WHERE kind=?', (kind,)).fetchone()
                    except sqlite3.OperationalError:
                        return None
            title, data = wait_for(captured)
            assert data == expected_data, (kind, data)
        finally:
            if app_process:
                app_process.terminate()
                app_process.communicate(timeout=5)
            source.terminate()
            source.communicate(timeout=5)
        os.environ['XDG_DATA_HOME'] = directory
        os.environ['XDG_CONFIG_HOME'] = directory
        history = History(db)
        assert history.list(title)[0][3] == kind
        history.close()
        app = App()
        manager_display = display.Display()
        manager = manager_display.get_selection_owner(manager_display.intern_atom('CLIPBOARD_MANAGER'))
        has_manager = bool(getattr(manager, 'id', manager))
        manager_display.close()
        try:
            row = next(row for row in app.rows.get_children() if row.kind == kind)
            app.choose(row, paste=False)
            if expected_output is None:
                expected_output = ('<b>Rich test</b>' if kind == 'rich' else
                                   "['file:///tmp/linuxxy-one.txt', 'file:///tmp/linuxxy-two.txt']")
            assert query(query_code) == expected_output
            if kind == 'rich':
                app.choose(row, paste=False, plain=True)
                plain = query("import gi;gi.require_version('Gtk','3.0');"
                              "gi.require_version('Gdk','3.0');from gi.repository import Gtk,Gdk;"
                              "c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);print(c.wait_for_text())")
                assert plain == title, plain
                assert app.history.list(title)[0][3] == 'rich'
                app.settings.set('remove_formatting_by_default', True)
                app.choose(row, paste=False)
                assert query("import gi;gi.require_version('Gtk','3.0');"
                             "gi.require_version('Gdk','3.0');from gi.repository import Gtk,Gdk;"
                             "c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);"
                             "print(c.wait_is_target_available(Gdk.atom_intern('text/html',False)))"
                             ) == 'False'
                app.choose(row, paste=False, plain=True)
                assert query(query_code) == expected_output
                app.settings.set('remove_formatting_by_default', False)
                app.choose(row, paste=False)
        finally:
            app.close()
        if has_manager:
            assert query(query_code) == expected_output, 'Clipboard was lost after Linuxxy exited'


def main():
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    original_image = clipboard.wait_for_image() if clipboard.wait_is_image_available() else None
    original_text = clipboard.wait_for_text() if original_image is None else None
    try:
        check('rich', {'UTF8_STRING': b'Rich test', 'text/plain;charset=utf-8': b'Rich test',
                       'text/html': b'<b>Rich test</b>'}, b'<b>Rich test</b>',
              "import gi;gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0');"
              "from gi.repository import Gtk,Gdk;c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);"
              "print(c.wait_for_contents(Gdk.atom_intern('text/html',False)).get_data().decode())")
        uri_data = b'file:///tmp/linuxxy-one.txt\r\nfile:///tmp/linuxxy-two.txt\r\n'
        check('files', {'text/uri-list': uri_data}, uri_data,
              "import gi;gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0');"
              "from gi.repository import Gtk,Gdk;c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);"
              "print(c.wait_for_uris())")
        large_html = b'<p>' + b'A' * 500_000 + b'</p>'
        check('rich', {'UTF8_STRING': b'Large HTML', 'text/html': large_html},
              large_html,
              "import gi,hashlib;gi.require_version('Gtk','3.0');"
              "gi.require_version('Gdk','3.0');from gi.repository import Gtk,Gdk;"
              "c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);"
              "print(hashlib.sha256(c.wait_for_contents(Gdk.atom_intern('text/html',False)).get_data()).hexdigest())",
              hashlib.sha256(large_html).hexdigest())
        large_uris = [f'file:///tmp/linuxxy-{index:05d}.txt' for index in range(10_000)]
        large_files = ('\r\n'.join(large_uris) + '\r\n').encode()
        check('files', {'text/uri-list': large_files}, large_files,
              "import gi;gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0');"
              "from gi.repository import Gtk,Gdk;c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);"
              "print(len(c.wait_for_uris()))", str(len(large_uris)))
        print('Small and large HTML and file URI round trips passed')
    finally:
        if original_image:
            clipboard.set_image(original_image)
        elif original_text is not None:
            clipboard.set_text(original_text, -1)
        clipboard.store()


if __name__ == '__main__':
    main()
