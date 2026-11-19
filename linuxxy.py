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
from x11 import X11


class App:
    def __init__(self):
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.history = History(data_home / "linuxxy" / "history.sqlite")
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard.connect("owner-change", self.on_clipboard_change)
        self.paused = False
        self.x11 = None
        self.return_window = None

        self.window = Gtk.Window(title="Linuxxy")
        self.window.set_default_size(440, 500)
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
        GLib.timeout_add(500, self.poll_clipboard)
        self.last_text = self.clipboard.wait_for_text()
        self.refresh()
        if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
            try:
                self.x11 = X11(self.toggle_window)
            except (RuntimeError, OSError) as error:
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
        for child in self.rows.get_children():
            self.rows.remove(child)
        for entry_id, value, pinned in self.history.list(self.search.get_text()):
            row = Gtk.ListBoxRow()
            row.entry_id, row.value, row.pinned = entry_id, value, bool(pinned)
            preview = " ".join(value.split())[:160]
            label = Gtk.Label(label=("📌 " if pinned else "") + preview, xalign=0)
            label.set_ellipsize(3)
            label.set_margin_top(5)
            label.set_margin_bottom(5)
            row.add(label)
            self.rows.add(row)
        self.rows.show_all()

    def selected(self):
        return self.rows.get_selected_row()

    def choose(self, row, paste=True):
        self.clipboard.set_text(row.value, -1)
        self.clipboard.store()
        self.last_text = row.value
        self.history.add(row.value)
        self.window.hide()
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
            self.choose(row)

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
        if event.keyval == Gdk.KEY_Escape:
            self.window.hide()
            return True
        if event.keyval == Gdk.KEY_Return:
            row = self.selected() or next(iter(self.rows.get_children()), None)
            if row:
                self.choose(row, paste=not bool(event.state & Gdk.ModifierType.CONTROL_MASK))
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
        return True

    def toggle_window(self):
        if self.window.get_visible():
            self.window.hide()
        else:
            if self.x11:
                self.return_window = self.x11.active_window()
            self.refresh()
            self.window.show_all()
            self.window.present()
            self.search.grab_focus()

    def tray_menu(self, _icon, button, activate_time):
        menu = Gtk.Menu()
        for label, callback in (("Open", self.toggle_window),
                                ("Resume monitoring" if self.paused else "Pause monitoring", self.toggle_pause),
                                ("Quit", self.quit)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, fn=callback: fn())
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, self.tray, button, activate_time)

    def toggle_pause(self):
        self.paused = not self.paused
        self.tray.set_tooltip_text("Linuxxy (paused)" if self.paused else "Linuxxy")

    def quit(self):
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
