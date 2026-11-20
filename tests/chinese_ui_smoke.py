"""Render simplified Chinese UI and switch languages in the real settings window."""

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


def descend(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descend(child)


clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
original = clipboard.wait_for_text()
clipboard.set_text(' ', -1)
clipboard.store()
try:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory,
                          XDG_RUNTIME_DIR=directory, XDG_SESSION_TYPE='x11')
        history = History(Path(directory) / 'linuxxy/history.sqlite')
        for value in ('欢迎使用剪贴板历史', '中文搜索与圆角测试', '复制的第三条内容'):
            history.add(value)
        history.close()
        settings = Settings()
        settings.set('language', 'zh_CN')
        settings.set('popup_position', 'screen_center')
        settings.set('open_preview_automatically', False)
        app = App()
        try:
            assert app.language == 'zh_CN'
            assert app.search.get_placeholder_text() == '搜索剪贴板历史'
            app.toggle_window()
            pump(.5)
            popup = GdkX11.X11Window.get_xid(app.window.get_window())
            screenshot(popup, 'ui_zh_popup.png')
            app.confirm_clear()
            pump(.3)
            dialog = next(window for window in Gtk.Window.list_toplevels()
                          if isinstance(window, Gtk.MessageDialog) and window.get_visible())
            assert any(isinstance(child, Gtk.Label) and
                       child.get_text() == '清除未置顶的剪贴板历史？'
                       for child in descend(dialog))
            screenshot(GdkX11.X11Window.get_xid(dialog.get_window()),
                       'ui_zh_clear_confirmation.png')
            dialog.response(Gtk.ResponseType.CANCEL)
            pump(.2)
            app.show_settings()
            pump(.4)
            assert app.preferences.get_title() == 'Linuxxy 设置'
            tabs = [child.get_text() for child in descend(app.preferences)
                    if isinstance(child, Gtk.Label)]
            notebook = next(child for child in descend(app.preferences)
                            if isinstance(child, Gtk.Notebook))
            tab_names = [notebook.get_tab_label(notebook.get_nth_page(index)).get_text()
                         for index in range(notebook.get_n_pages())]
            assert '通用' in tab_names and '外观' in tab_names and '开机自启' in tabs, (
                tab_names, tabs)
            settings_xid = GdkX11.X11Window.get_xid(app.preferences.get_window())
            screenshot(settings_xid, 'ui_zh_settings.png')
            notebook.set_current_page(2)
            pump(.3)
            screenshot(settings_xid, 'ui_zh_appearance.png')
            appearance = notebook.get_nth_page(2)
            adjustment = appearance.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            pump(.3)
            screenshot(settings_xid, 'ui_zh_language_setting.png')
            language = next(child for child in descend(app.preferences)
                            if child.get_name() == 'linuxxy-language-setting')
            assert [row[0] for row in language.get_model()] == [
                '跟随系统语言', '简体中文', 'English']
            language.set_active_id('en')
            save = next(child for child in descend(app.preferences)
                        if isinstance(child, Gtk.Button) and child.get_label() == '保存')
            save.clicked()
            pump(.3)
            assert Settings().get('language') == 'en'
            assert app.search.get_placeholder_text() == 'Search clipboard history'
            app.toggle_window()
            pump(.3)
            app.show_settings()
            pump(.3)
            assert app.preferences.get_title() == 'Linuxxy Preferences'
            app.preferences.destroy()
            print('Chinese popup, settings, glyphs, and language switching passed')
        finally:
            app.quit()
finally:
    if original is not None:
        clipboard.set_text(original, -1)
        clipboard.store()
