"""Render the current popup and settings pages for visual review."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'screenshots'
OUT.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_DATA_HOME'] = directory
    os.environ['XDG_CONFIG_HOME'] = directory
    from history import History
    history = History(Path(directory) / 'linuxxy/history.sqlite')
    history.add('linuxxy-sample second item')
    history.add('linuxxy-sample pinned item')
    history.pin(history.list()[0][0], True)
    history.close()

    from linuxxy import App
    from gi.repository import Gtk, GLib, GdkX11
    app = App()
    app.search.set_text('linuxxy-sample')
    app.toggle_window()

    def shot(window, name):
        xid = GdkX11.X11Window.get_xid(window.get_window())
        raw = Path(directory) / 'shot.xwd'
        subprocess.run(['xwd', '-silent', '-id', hex(xid), '-out', str(raw)],
                       check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw),
                        '-frames:v', '1', str(OUT / name)], check=True, capture_output=True)

    def render():
        shot(app.window, 'popup.png')
        app.show_settings()
        notebook = app.preferences.get_child().get_children()[0]
        def page(number):
            notebook.set_current_page(number)
            def take():
                shot(app.preferences, ('general.png', 'storage.png', 'appearance.png')[number])
                if number < 2:
                    page(number + 1)
                else:
                    app.preferences.destroy()
                    app.quit()
                return False
            GLib.timeout_add(150, take)
        page(0)
        return False

    GLib.timeout_add(550, render)
    Gtk.main()
    print('visual samples saved in', OUT)
