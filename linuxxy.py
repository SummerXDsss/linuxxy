#!/usr/bin/env python3
"""Linuxxy: a searchable clipboard history for X11 desktops."""

import os
import signal
import fcntl
import hashlib
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from history import History
from autostart import set_enabled as set_autostart
from settings import Settings
from x11 import X11
from x11_clipboard import X11Clipboard


class App:
    def __init__(self):
        self.settings = Settings()
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.history = History(data_home / "linuxxy" / "history.sqlite",
                               limit=self.settings.get("history_size"))
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard_handler = self.clipboard.connect("owner-change", self.on_clipboard_change)
        self.closed = False
        self.paused = False
        self.x11 = None
        self.rich_clipboard = None
        self.return_window = None
        self.ignore_own_change_until = 0

        self.window = Gtk.Window(title="Linuxxy")
        self.window.set_default_size(440, 120)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.set_name("linuxxy-popup")
        self.window.connect("delete-event", self.hide_window)
        self.window.connect("key-press-event", self.on_key)
        self.install_style()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_border_width(7)
        self.window.add(box)
        self.search = Gtk.SearchEntry()
        self.search.set_name("linuxxy-search")
        self.search.set_placeholder_text("Search clipboard history")
        self.search.connect("changed", lambda *_: GLib.idle_add(self.refresh))
        self.search.connect("key-press-event", self.search_key)
        box.pack_start(self.search, False, False, 3)
        box.pack_start(Gtk.Separator(), False, False, 4)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scroll, True, True, 0)
        self.rows = Gtk.ListBox()
        self.rows.set_name("linuxxy-list")
        self.rows.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.rows.connect("row-activated", lambda _list, row: self.choose(row))
        self.rows.connect("row-selected", self.mark_selected)
        scroll.add(self.rows)
        box.pack_start(Gtk.Separator(), False, False, 4)
        footer = Gtk.Box(spacing=6)
        footer.set_name("linuxxy-footer")
        footer.set_no_show_all(not self.settings.get("show_footer"))
        self.footer = footer
        box.pack_start(footer, False, False, 0)
        for label, callback in (("Clear", self.clear), ("Preferences", self.show_settings),
                                ("Quit", self.quit)):
            button = Gtk.Button(label=label)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", callback)
            footer.pack_start(button, False, False, 0)
        hint = Gtk.Label(label="↵ Copy  ·  Alt+↵ Paste")
        hint.set_xalign(1)
        footer.pack_end(hint, False, False, 4)

        self.tray = Gtk.StatusIcon.new_from_icon_name("edit-paste")
        self.tray.set_tooltip_text("Linuxxy")
        self.tray.connect("activate", lambda *_: self.toggle_window())
        self.tray.connect("popup-menu", self.tray_menu)
        self.poll_id = GLib.timeout_add(self.settings.get("check_interval_ms"), self.poll_clipboard)
        self.last_signature = None
        self.capture()
        self.refresh()
        if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
            try:
                self.rich_clipboard = X11Clipboard()
            except (RuntimeError, OSError) as error:
                print(f"Clipboard formats unavailable: {error}")
            try:
                self.x11 = X11(self.toggle_window, self.settings.get("shortcut"))
            except (RuntimeError, OSError, ValueError) as error:
                print(f"Global shortcut unavailable: {error}")

    def install_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            #linuxxy-popup { background: #28292d; border: 1px solid #4a4b50; border-radius: 9px; }
            #linuxxy-search { min-height: 30px; margin: 2px 2px 4px 2px; }
            #linuxxy-list, #linuxxy-list > row { background: transparent; }
            #linuxxy-list > row { min-height: 31px; border-radius: 5px; }
            box.linuxxy-selected { background-color: #466ca8; border-radius: 5px; color: white; }
            #linuxxy-footer button { min-height: 20px; padding: 0 6px; font-size: 11px; }
            #linuxxy-footer label { color: #aaa; font-size: 11px; }
            #linuxxy-index { color: #aaa; font-size: 10px; min-width: 16px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_clipboard_change(self, *_):
        GLib.idle_add(self.capture, time.monotonic() > self.ignore_own_change_until)

    def poll_clipboard(self):
        self.capture()
        return True

    def capture(self, force=False):
        if self.closed:
            return False
        if self.rich_clipboard and self.rich_clipboard.is_owner():
            return False
        uris = self.clipboard.wait_for_uris() if self.clipboard.wait_is_uris_available() else None
        uris = [uri for uri in uris or [] if uri.startswith("file://")]
        image = None
        text = None
        html = None
        if uris:
            signature = ("files", tuple(uris))
        elif self.clipboard.wait_is_image_available():
            image = self.clipboard.wait_for_image()
            if image:
                ok, data = image.save_to_bufferv("png", [], [])
                signature = ("image", hashlib.sha256(data).digest()) if ok else None
            else:
                signature = None
        else:
            text = self.clipboard.wait_for_text()
            target = Gdk.atom_intern("text/html", False)
            if text and self.clipboard.wait_is_target_available(target):
                selection = self.clipboard.wait_for_contents(target)
                html = selection.get_data() if selection else None
            signature = ("rich", text, hashlib.sha256(html).digest()) if html else ("text", text)
        if signature != self.last_signature or force:
            self.last_signature = signature
            if not self.paused:
                if uris and self.settings.get("save_files"):
                    self.history.add_files(uris)
                elif image and signature and self.settings.get("save_images"):
                    self.history.add_image(data)
                elif html and text and self.settings.get("save_text"):
                    self.history.add_rich(text, html)
                elif text and self.settings.get("save_text"):
                    self.history.add(text)
                self.refresh()
        return False

    def refresh(self):
        selected = self.selected()
        selected_id = selected.entry_id if selected else None
        for child in self.rows.get_children():
            self.rows.remove(child)
        restored = None
        previous_pin = None
        row_count = 0
        image_count = 0
        for index, (entry_id, value, pinned, kind, data) in enumerate(self.history.list(
            self.search.get_text(), self.settings.get("search_mode"),
            self.settings.get("pins_position")
        )):
            row = Gtk.ListBoxRow()
            row.set_name("linuxxy-row")
            row.entry_id, row.value, row.pinned = entry_id, value, bool(pinned)
            row.kind, row.data = kind, data
            row.connect("button-press-event", self.row_click)
            if previous_pin is not None and previous_pin != pinned:
                row.set_header(Gtk.Separator())
            previous_pin = pinned
            if kind == "image" and data:
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                scale = min(1, 64 / max(pixbuf.get_width(), pixbuf.get_height()))
                thumbnail = pixbuf.scale_simple(max(1, int(pixbuf.get_width() * scale)),
                                                max(1, int(pixbuf.get_height() * scale)),
                                                GdkPixbuf.InterpType.BILINEAR)
                visual = Gtk.Image.new_from_pixbuf(thumbnail)
                preview = "Image"
                image_count += 1
            else:
                visual = None
                preview = " ".join(value.split())[:160]
                if kind == "files":
                    preview = preview.rsplit(" ", 1)[0]
            label = Gtk.Label(label=preview, xalign=0)
            label.set_ellipsize(3)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            if kind == "text":
                row.set_tooltip_text(value[:10000])
            content = Gtk.Box(spacing=8)
            content.set_border_width(4)
            row.content = content
            if pinned:
                content.pack_start(Gtk.Image.new_from_icon_name("emblem-favorite", Gtk.IconSize.MENU),
                                   False, False, 2)
            if kind == "files":
                content.pack_start(Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.MENU),
                                   False, False, 2)
            if visual:
                content.pack_start(visual, False, False, 0)
            content.pack_start(label, True, True, 0)
            if index < 9:
                badge = Gtk.Label(label=str(index + 1))
                badge.set_name("linuxxy-index")
                content.pack_end(badge, False, False, 4)
            row.add(content)
            self.rows.add(row)
            row_count += 1
            if entry_id == selected_id:
                restored = row
        self.rows.show_all()
        if restored:
            self.rows.select_row(restored)
        elif self.rows.get_children():
            self.rows.select_row(self.rows.get_children()[0])
        self.resize_popup(row_count, image_count)

    def resize_popup(self, count, image_count=0):
        # Match the content instead of leaving a large empty window behind.
        visible = min(count, 9)
        height = 105 + max(34, visible * 40 + min(image_count, visible) * 30)
        if not self.settings.get("show_footer"):
            height -= 26
        self.window.resize(440, min(height, 470))

    def row_click(self, row, event):
        if event.button == 1:
            alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
            shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
            self.choose(row, paste=True if alt else None, plain=alt and shift)
            return True
        if event.button != 3:
            return False
        self.rows.select_row(row)
        menu = Gtk.Menu()
        for label, callback in (("Paste", self.paste_selected),
                                ("Copy", self.copy_selected),
                                ("Preview", self.show_preview),
                                ("Unpin" if row.pinned else "Pin", self.toggle_pin),
                                ("Delete", self.delete_selected)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, fn=callback: fn())
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def selected(self):
        return self.rows.get_selected_row()

    def mark_selected(self, _list, selected):
        for row in self.rows.get_children():
            row.content.get_style_context().remove_class("linuxxy-selected")
        if selected:
            selected.content.get_style_context().add_class("linuxxy-selected")

    def choose(self, row, paste=None, plain=False):
        if paste is None:
            paste = self.settings.get("paste_by_default")
        if plain and row.kind == "rich":
            self.ignore_own_change_until = time.monotonic() + 0.5
            self.clipboard.set_text(row.value, -1)
            self.last_signature = ("text", row.value)
            self.history.add_rich(row.value, row.data)
        elif row.kind == "files" and self.rich_clipboard:
            uris = row.data.decode("utf-8").splitlines()
            self.rich_clipboard.set({
                "text/uri-list": row.data,
                "x-special/gnome-copied-files": ("copy\n" + "\n".join(uris)).encode("utf-8"),
            })
            self.last_signature = ("files", tuple(uris))
            self.history.add_files(uris)
        elif row.kind == "rich" and self.rich_clipboard:
            text = row.value.encode("utf-8")
            self.rich_clipboard.set({
                "UTF8_STRING": text,
                "text/plain;charset=utf-8": text,
                "text/html": row.data,
            })
            self.last_signature = ("rich", row.value, hashlib.sha256(row.data).digest())
            self.history.add_rich(row.value, row.data)
        elif row.kind == "image":
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(row.data)
            loader.close()
            self.clipboard.set_image(loader.get_pixbuf())
            self.last_signature = ("image", hashlib.sha256(row.data).digest())
            self.history.add_image(row.data)
        else:
            self.clipboard.set_text(row.value, -1)
            self.last_signature = ("text", row.value)
            if row.kind == "text":
                self.history.add(row.value)
        if not (row.kind in ("files", "rich") and self.rich_clipboard):
            self.clipboard.store()
        self.window.hide()
        self.search.set_text("")
        self.refresh()
        if paste and self.x11 and self.return_window:
            self.x11.activate(self.return_window)
            self.paste_attempts = 0
            GLib.timeout_add(50, self.delayed_paste)

    def delayed_paste(self):
        self.paste_attempts += 1
        if self.x11 and self.x11.active_window() == self.return_window:
            self.x11.paste()
            return False
        if self.paste_attempts < 20:
            return True
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
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if ctrl or alt:
            digit = Gdk.keyval_name(event.keyval)
            if digit and digit in "123456789":
                rows = self.rows.get_children()
                if int(digit) <= len(rows):
                    self.choose(rows[int(digit) - 1], paste=alt)
                return True
        if event.keyval == Gdk.KEY_comma and ctrl:
            self.show_settings()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.hide_window()
            return True
        if event.keyval == Gdk.KEY_p and alt:
            self.toggle_pin()
            return True
        if event.keyval == Gdk.KEY_Delete and ctrl and alt:
            if shift:
                self.history.clear_all()
            else:
                self.history.clear()
            self.refresh()
            return True
        if event.keyval == Gdk.KEY_Delete and alt:
            self.delete_selected()
            return True
        if event.keyval == Gdk.KEY_space and self.selected() and not self.search.is_focus():
            self.show_preview()
            return True
        if event.keyval == Gdk.KEY_Return:
            row = self.selected() or next(iter(self.rows.get_children()), None)
            if row:
                if alt and shift:
                    self.choose(row, paste=True, plain=True)
                elif alt or ctrl:
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
            self.hide_window()
        else:
            if self.x11:
                self.return_window = self.x11.active_window()
            self.refresh()
            if self.settings.get("popup_at_cursor"):
                display = Gdk.Display.get_default()
                _screen, x, y, _mods = display.get_pointer()
                monitor = display.get_monitor_at_point(x, y)
                work = monitor.get_workarea()
                width, height = self.window.get_size()
                x = max(work.x, min(x, work.x + work.width - width))
                y = max(work.y, min(y, work.y + work.height - height))
                self.window.move(x, y)
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
        self.window.hide()
        window = Gtk.Window(title="Linuxxy Preferences")
        window.set_default_size(460, 320)
        window.set_border_width(14)
        window.set_transient_for(self.window)
        window.set_keep_above(True)
        window.connect("destroy", lambda *_: setattr(self, "preferences", None))
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        window.add(layout)
        notebook = Gtk.Notebook()
        layout.pack_start(notebook, True, True, 0)
        grids = {}
        for title in ("General", "Storage", "Appearance"):
            grid = Gtk.Grid(column_spacing=16, row_spacing=14)
            grid.set_border_width(16)
            notebook.append_page(grid, Gtk.Label(label=title))
            grids[title] = grid

        def field(grid, row, label, widget):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

        shortcut = Gtk.Entry(text=self.settings.get("shortcut"))
        shortcut.set_tooltip_text("Example: Super+Shift+V")
        field(grids["General"], 0, "Open shortcut", shortcut)
        paste = Gtk.CheckButton(label="Paste by default (Alt+Enter reverses)")
        paste.set_active(self.settings.get("paste_by_default"))
        grids["General"].attach(paste, 0, 1, 2, 1)
        search_mode = Gtk.ComboBoxText()
        for key, label in (("exact", "Exact"), ("fuzzy", "Fuzzy"),
                           ("regex", "Regular expression"), ("mixed", "Mixed")):
            search_mode.append(key, label)
        search_mode.set_active_id(self.settings.get("search_mode"))
        field(grids["General"], 2, "Search mode", search_mode)
        launch_at_login = Gtk.CheckButton(label="Launch at login")
        launch_at_login.set_active(self.settings.get("launch_at_login"))
        grids["General"].attach(launch_at_login, 0, 3, 2, 1)

        size = Gtk.SpinButton.new_with_range(1, 10000, 1)
        size.set_value(self.settings.get("history_size"))
        save_text = Gtk.CheckButton(label="Save text")
        save_text.set_active(self.settings.get("save_text"))
        grids["Storage"].attach(save_text, 0, 0, 2, 1)
        save_images = Gtk.CheckButton(label="Save images")
        save_images.set_active(self.settings.get("save_images"))
        grids["Storage"].attach(save_images, 0, 1, 2, 1)
        save_files = Gtk.CheckButton(label="Save files")
        save_files.set_active(self.settings.get("save_files"))
        grids["Storage"].attach(save_files, 0, 2, 2, 1)
        field(grids["Storage"], 3, "History items", size)
        interval = Gtk.SpinButton.new_with_range(100, 5000, 100)
        interval.set_value(self.settings.get("check_interval_ms"))
        field(grids["Storage"], 4, "Clipboard check (ms)", interval)
        clear_on_quit = Gtk.CheckButton(label="Clear history on quit")
        clear_on_quit.set_active(self.settings.get("clear_on_quit"))
        grids["Storage"].attach(clear_on_quit, 0, 5, 2, 1)

        pins_position = Gtk.ComboBoxText()
        pins_position.append("top", "Top")
        pins_position.append("bottom", "Bottom")
        pins_position.set_active_id(self.settings.get("pins_position"))
        field(grids["Appearance"], 0, "Pinned items", pins_position)
        position = Gtk.CheckButton(label="Open near pointer")
        position.set_active(self.settings.get("popup_at_cursor"))
        grids["Appearance"].attach(position, 0, 1, 2, 1)
        show_footer = Gtk.CheckButton(label="Show footer")
        show_footer.set_active(self.settings.get("show_footer"))
        grids["Appearance"].attach(show_footer, 0, 2, 2, 1)
        buttons = Gtk.Box(spacing=8)
        layout.pack_end(buttons, False, False, 0)
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
                ("save_text", save_text.get_active()),
                ("save_images", save_images.get_active()),
                ("save_files", save_files.get_active()),
                ("check_interval_ms", interval.get_value_as_int()),
                ("search_mode", search_mode.get_active_id()),
                ("pins_position", pins_position.get_active_id()),
                ("popup_at_cursor", position.get_active()),
                ("show_footer", show_footer.get_active()),
                ("clear_on_quit", clear_on_quit.get_active()),
                ("launch_at_login", launch_at_login.get_active()),
            ):
                self.settings.set(key, value, save=False)
            self.settings.save()
            set_autostart(self.settings.get("launch_at_login"))
            self.history.set_limit(self.settings.get("history_size"))
            self.footer.set_no_show_all(not self.settings.get("show_footer"))
            self.footer.set_visible(self.settings.get("show_footer"))
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

    def show_preview(self):
        row = self.selected()
        if not row:
            return
        if getattr(self, "preview", None):
            self.preview.destroy()
        window = Gtk.Window(title="Linuxxy Preview")
        window.set_transient_for(self.window)
        window.set_default_size(600, 420)
        window.connect("key-press-event", lambda _w, event: self.close_preview(event))
        window.connect("destroy", lambda *_: setattr(self, "preview", None))
        scroll = Gtk.ScrolledWindow()
        window.add(scroll)
        if row.kind == "image":
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(row.data)
            loader.close()
            image = Gtk.Image.new_from_pixbuf(loader.get_pixbuf())
            scroll.add_with_viewport(image)
        else:
            text = Gtk.TextView()
            text.set_editable(False)
            text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            text.set_monospace(True)
            text.set_left_margin(12)
            text.set_right_margin(12)
            text.get_buffer().set_text(
                row.data.decode("utf-8").replace("\r", "") if row.kind == "files" else row.value
            )
            scroll.add(text)
        self.preview = window
        window.show_all()
        window.present()

    def close_preview(self, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_space):
            self.preview.destroy()
            return True
        return False

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.clipboard.disconnect(self.clipboard_handler)
        if GLib.MainContext.default().find_source_by_id(self.poll_id):
            GLib.source_remove(self.poll_id)
        if self.settings.get("clear_on_quit"):
            self.history.clear_all()
        if self.x11:
            self.x11.close()
        if self.rich_clipboard:
            self.rich_clipboard.close()
        self.history.close()

    def quit(self):
        self.close()
        if Gtk.main_level():
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
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                         lambda *_: (app.quit(), False)[1])
    Gtk.main()
