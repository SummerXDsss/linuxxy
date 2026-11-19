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
    history.add_rich('linuxxy-sample formatted text', b'<b>linuxxy-sample formatted text</b>')
    history.add_files(['file:///tmp/linuxxy-sample-document.txt'])
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 160, 80)
    image.fill(0x4e9aabff)
    ok, png = image.save_to_bufferv('png', [], [])
    assert ok
    history.add_image(png)
    history.add('#4e9aab')
    history.add('  linuxxy-sample\nnext\tline  ')
    history.close()

    from settings import Settings
    Settings().set('preview_delay_ms', 200)
    from linuxxy import App
    from gi.repository import Gtk, GLib, Gdk, GdkX11
    app = App()
    app.search.set_text('')
    app.toggle_window()

    def shot(window, name):
        xid = GdkX11.X11Window.get_xid(window.get_window())
        raw = Path(directory) / 'shot.xwd'
        try:
            subprocess.run(['xwd', '-silent', '-id', hex(xid), '-out', str(raw)],
                           check=True, capture_output=True)
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw),
                            '-frames:v', '1', str(OUT / name)], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # A compositing desktop can deny XGetImage for a visible window.
            drawable = window.get_window()
            width, height = drawable.get_geometry()[2:4]
            pixbuf = Gdk.pixbuf_get_from_window(drawable, 0, 0, width, height)
            if pixbuf is None:
                raise
            pixbuf.savev(str(OUT / name), 'png', [], [])

    def render():
        try:
            app.rows.select_row(app.rows.get_children()[1])
            assert app.preview is app.preview_pane
            assert app.preview_entry_id == app.rows.get_children()[1].entry_id
            app.cancel_preview()
        except Exception:
            app.quit()
            raise
        GLib.timeout_add(150, render_closed)
        return False

    def render_closed():
        try:
            assert app.window.get_size()[0] == app.content_width
            shot(app.window, 'popup.png')
            app.settings.set('preview_delay_ms', 1500, save=False)
            app.show_settings()
        except Exception:
            app.quit()
            raise
        notebook = app.preferences.get_child().get_children()[0]
        def page(number):
            notebook.set_current_page(number)
            def take():
                try:
                    shot(app.preferences, ('general.png', 'storage.png',
                                           'appearance.png', 'advanced.png')[number])
                except Exception:
                    app.quit()
                    raise
                if number < 3:
                    if number == 2:
                        appearance_scroll = notebook.get_nth_page(2)
                        adjustment = appearance_scroll.get_vadjustment()
                        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
                        def bottom():
                            shot(app.preferences, 'appearance_tray.png')
                            page(3)
                            return False
                        GLib.timeout_add(150, bottom)
                    else:
                        page(number + 1)
                else:
                    appearance = notebook.get_nth_page(2).get_child().get_child()
                    search_options = next(widget for widget in appearance.get_children()
                                          if isinstance(widget, Gtk.Box) and any(
                                              isinstance(child, Gtk.CheckButton) and
                                              child.get_label() == 'Show search field'
                                              for child in widget.get_children()))
                    search_toggle = next(widget for widget in search_options.get_children()
                                         if isinstance(widget, Gtk.CheckButton))
                    search_mode = next(widget for widget in search_options.get_children()
                                       if isinstance(widget, Gtk.ComboBoxText))
                    search_mode.set_active_id('during_search')
                    search_toggle.set_active(False)
                    popup_position = next(widget for widget in appearance.get_children()
                                          if isinstance(widget, Gtk.ComboBoxText) and
                                          widget.get_active_id() == 'cursor')
                    popup_position.set_active_id('screen_center')
                    buttons = app.preferences.get_child().get_children()[-1]
                    save = next(widget for widget in buttons.get_children()
                                if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save')
                    save.clicked()
                    assert app.settings.get('search_visibility') == 'during_search'
                    assert app.settings.get('show_search_field') is False
                    assert app.settings.get('popup_position') == 'screen_center'
                    persisted = Settings()
                    assert persisted.get('search_visibility') == 'during_search'
                    assert persisted.get('show_search_field') is False
                    assert persisted.get('popup_position') == 'screen_center'
                    app.quit()
                return False
            GLib.timeout_add(150, take)
        page(0)
        return False

    def render_preview():
        assert app.preview is app.preview_pane and app.preview_auto
        assert app.preview_pane.get_visible() and app.window.get_size()[0] > 440
        shot(app.window, 'auto_preview.png')
        return False

    GLib.timeout_add(400, render_preview)
    GLib.timeout_add(550, render)
    Gtk.main()
    print('visual samples saved in', OUT)
