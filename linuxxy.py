#!/usr/bin/env python3
"""Linuxxy: a searchable clipboard history for X11 desktops."""

import os
import signal
import fcntl
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from history import History
from autostart import set_enabled as set_autostart
from settings import Settings
from x11 import X11


class App:
    def __init__(self):
        self.settings = Settings()
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.history = History(data_home / "linuxxy" / "history.sqlite",
                               limit=self.settings.get("history_size"))
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard.connect("owner-change", self.on_clipboard_change)
        self.paused = False
        self.x11 = None
        self.return_window = None

        self.window = Gtk.Window(title="Linuxxy")
        self.window.set_default_size(440, 500)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.connect("delete-event", self.hide_window)
        self.window.connect("key-press-event", self.on_key)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)
        self.window.add(box)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search clipboard history")
        self.search.connect("search-changed", lambda *_: self.refresh())
        self.search.connect("key-press-event", self.search_key)
        box.pack_start(self.search, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        box.pack_start(scroll, True, True, 0)
        self.rows = Gtk.ListBox()
        self.rows.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.rows.connect("row-activated", self.choose)
        scroll.add(self.rows)
        buttons = Gtk.Box(spacing=6)
        box.pack_start(buttons, False, False, 0)
        for label, callback in (("Paste", self.paste_selected), ("Copy", self.copy_selected),
                                ("Pin / Unpin", self.toggle_pin),
                                ("Delete", self.delete_selected), ("Clear unpinned", self.clear)):
            button = Gtk.Button(label=label)
            button.connect("clicked", callback)
            buttons.pack_start(button, True, True, 0)

        self.tray = Gtk.StatusIcon.new_from_icon_name("edit-paste")
        self.tray.set_tooltip_text("Linuxxy")
        self.tray.connect("activate", lambda *_: self.toggle_window())
        self.tray.connect("popup-menu", self.tray_menu)
        self.poll_id = GLib.timeout_add(self.settings.get("check_interval_ms"), self.poll_clipboard)
        self.last_text = self.clipboard.wait_for_text()
        self.refresh()
        if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
            try:
                self.x11 = X11(self.toggle_window, self.settings.get("shortcut"))
            except (RuntimeError, OSError, ValueError) as error:
                print(f"Global shortcut unavailable: {error}")

    def on_clipboard_change(self, *_):
        GLib.idle_add(self.capture)

    def poll_clipboard(self):
        self.capture()
        return True

    def capture(self):
        text = self.clipboard.wait_for_text()
        if text != self.last_text:
            self.last_text = text
            if not self.paused and text:
                self.history.add(text)
                self.refresh()
        return False

    def refresh(self):
        selected = self.selected()
        selected_id = selected.entry_id if selected else None
        for child in self.rows.get_children():
            self.rows.remove(child)
        restored = None
        for entry_id, value, pinned in self.history.list(
            self.search.get_text(), self.settings.get("search_mode"),
            self.settings.get("pins_position")
        ):
            row = Gtk.ListBoxRow()
            row.entry_id, row.value, row.pinned = entry_id, value, bool(pinned)
            preview = " ".join(value.split())[:160]
            label = Gtk.Label(label=("📌 " if pinned else "") + preview, xalign=0)
            label.set_ellipsize(3)
            label.set_margin_top(5)
            label.set_margin_bottom(5)
            row.add(label)
            self.rows.add(row)
            if entry_id == selected_id:
                restored = row
        self.rows.show_all()
        if restored:
            self.rows.select_row(restored)

    def selected(self):
        return self.rows.get_selected_row()

    def choose(self, row, paste=None):
        if paste is None:
            paste = self.settings.get("paste_by_default")
        self.clipboard.set_text(row.value, -1)
        self.clipboard.store()
        self.last_text = row.value
        self.history.add(row.value)
        self.window.hide()
        self.search.set_text("")
        self.refresh()
        if paste and self.x11 and self.return_window:
            self.x11.activate(self.return_window)
            GLib.timeout_add(180, self.delayed_paste)

    def delayed_paste(self):
        if self.x11:
            self.x11.paste()
        return False

    def paste_selected(self, *_):
        if row := self.selected():
            self.choose(row, paste=True)

    def copy_selected(self, *_):
        if row := self.selected():
            self.choose(row, paste=False)

    def toggle_pin(self, *_):
        if row := self.selected():
            self.history.pin(row.entry_id, not row.pinned)
            self.refresh()

    def delete_selected(self, *_):
        if row := self.selected():
            self.history.delete(row.entry_id)
            self.refresh()

    def clear(self, *_):
        self.history.clear()
        self.refresh()

    def on_key(self, _window, event):
        if event.keyval == Gdk.KEY_comma and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.show_settings()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.window.hide()
            return True
        if event.keyval == Gdk.KEY_p and event.state & Gdk.ModifierType.MOD1_MASK:
            self.toggle_pin()
            return True
        if event.keyval == Gdk.KEY_Delete and event.state & Gdk.ModifierType.MOD1_MASK:
            self.delete_selected()
            return True
        if event.keyval == Gdk.KEY_Return:
            row = self.selected() or next(iter(self.rows.get_children()), None)
            if row:
                if event.state & Gdk.ModifierType.CONTROL_MASK:
                    self.choose(row, paste=not self.settings.get("paste_by_default"))
                else:
                    self.choose(row)
            return True
        return False

    def search_key(self, _search, event):
        if event.keyval == Gdk.KEY_Return:
            return self.on_key(self.window, event)
        if event.keyval == Gdk.KEY_Down:
            first = next(iter(self.rows.get_children()), None)
            if first:
                self.rows.select_row(first)
                first.grab_focus()
            return True
        return False

    def hide_window(self, *_):
        self.window.hide()
        self.search.set_text("")
        return True

    def toggle_window(self):
        if self.window.get_visible():
            self.window.hide()
        else:
            if self.x11:
                self.return_window = self.x11.active_window()
            if self.settings.get("popup_at_cursor"):
                display = Gdk.Display.get_default()
                _screen, x, y, _mods = display.get_pointer()
                self.window.move(x, y)
            self.refresh()
            self.window.show_all()
            self.window.present()
            self.search.grab_focus()

    def tray_menu(self, _icon, button, activate_time):
        menu = Gtk.Menu()
        for label, callback in (("Open", self.toggle_window),
                                ("Preferences…", self.show_settings),
                                ("Resume monitoring" if self.paused else "Pause monitoring", self.toggle_pause),
                                ("Quit", self.quit)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, fn=callback: fn())
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, self.tray, button, activate_time)

    def show_settings(self, *_):
        if getattr(self, "preferences", None) and self.preferences.get_visible():
            self.preferences.present()
            return
        window = Gtk.Window(title="Linuxxy Preferences")
        window.set_default_size(410, 300)
        window.set_border_width(16)
        window.set_transient_for(self.window)
        window.connect("destroy", lambda *_: setattr(self, "preferences", None))
        grid = Gtk.Grid(column_spacing=14, row_spacing=12)
        window.add(grid)

        def field(row, label, widget):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

        shortcut = Gtk.Entry(text=self.settings.get("shortcut"))
        shortcut.set_tooltip_text("Example: Super+Shift+V")
        field(0, "Open shortcut", shortcut)
        paste = Gtk.CheckButton(label="Paste by default (Ctrl+Enter reverses)")
        paste.set_active(self.settings.get("paste_by_default"))
        grid.attach(paste, 0, 1, 2, 1)
        size = Gtk.SpinButton.new_with_range(1, 10000, 1)
        size.set_value(self.settings.get("history_size"))
        field(2, "History items", size)
        interval = Gtk.SpinButton.new_with_range(100, 5000, 100)
        interval.set_value(self.settings.get("check_interval_ms"))
        field(3, "Clipboard check (ms)", interval)
        search_mode = Gtk.ComboBoxText()
        for key, label in (("exact", "Exact"), ("fuzzy", "Fuzzy"),
                           ("regex", "Regular expression"), ("mixed", "Mixed")):
            search_mode.append(key, label)
        search_mode.set_active_id(self.settings.get("search_mode"))
        field(4, "Search mode", search_mode)
        pins_position = Gtk.ComboBoxText()
        pins_position.append("top", "Top")
        pins_position.append("bottom", "Bottom")
        pins_position.set_active_id(self.settings.get("pins_position"))
        field(5, "Pinned items", pins_position)
        position = Gtk.CheckButton(label="Open near pointer")
        position.set_active(self.settings.get("popup_at_cursor"))
        grid.attach(position, 0, 6, 2, 1)
        clear_on_quit = Gtk.CheckButton(label="Clear history on quit")
        clear_on_quit.set_active(self.settings.get("clear_on_quit"))
        grid.attach(clear_on_quit, 0, 7, 2, 1)
        launch_at_login = Gtk.CheckButton(label="Launch at login")
        launch_at_login.set_active(self.settings.get("launch_at_login"))
        grid.attach(launch_at_login, 0, 8, 2, 1)
        buttons = Gtk.Box(spacing=8)
        grid.attach(buttons, 0, 9, 2, 1)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: window.destroy())
        buttons.pack_end(cancel, False, False, 0)
        save = Gtk.Button(label="Save")
        save.get_style_context().add_class("suggested-action")
        buttons.pack_end(save, False, False, 0)

        def apply(*_):
            new_shortcut = shortcut.get_text().strip()
            new_x11 = None
            try:
                from x11 import parse_shortcut
                parse_shortcut(new_shortcut)
                if self.x11 and new_shortcut != self.settings.get("shortcut"):
                    new_x11 = X11(self.toggle_window, new_shortcut)
                elif not self.x11 and os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
                    new_x11 = X11(self.toggle_window, new_shortcut)
            except (ValueError, RuntimeError, OSError) as error:
                alert = Gtk.MessageDialog(transient_for=window, modal=True,
                                          message_type=Gtk.MessageType.ERROR,
                                          buttons=Gtk.ButtonsType.CLOSE,
                                          text=str(error))
                alert.run()
                alert.destroy()
                return
            if new_x11:
                if self.x11:
                    self.x11.close()
                self.x11 = new_x11
            for key, value in (
                ("shortcut", new_shortcut),
                ("paste_by_default", paste.get_active()),
                ("history_size", size.get_value_as_int()),
                ("check_interval_ms", interval.get_value_as_int()),
                ("search_mode", search_mode.get_active_id()),
                ("pins_position", pins_position.get_active_id()),
                ("popup_at_cursor", position.get_active()),
                ("clear_on_quit", clear_on_quit.get_active()),
                ("launch_at_login", launch_at_login.get_active()),
            ):
                self.settings.set(key, value, save=False)
            self.settings.save()
            set_autostart(self.settings.get("launch_at_login"))
            self.history.set_limit(self.settings.get("history_size"))
            GLib.source_remove(self.poll_id)
            self.poll_id = GLib.timeout_add(self.settings.get("check_interval_ms"), self.poll_clipboard)
            self.refresh()
            window.destroy()

        save.connect("clicked", apply)
        self.preferences = window
        window.show_all()
        window.present()

    def toggle_pause(self):
        self.paused = not self.paused
        self.tray.set_tooltip_text("Linuxxy (paused)" if self.paused else "Linuxxy")

    def quit(self):
        if self.settings.get("clear_on_quit"):
            self.history.clear_all()
        if self.x11:
            self.x11.close()
        self.history.close()
        Gtk.main_quit()


if __name__ == "__main__":
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    lock_path = runtime_dir / f"linuxxy-{os.getuid()}.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Linuxxy is already running")
        raise SystemExit(1)
    app = App()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    Gtk.main()
