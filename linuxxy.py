#!/usr/bin/env python3
"""Linuxxy: a searchable clipboard history for X11 desktops."""

import os
import signal
import fcntl
import hashlib
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from Xlib.error import XError

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from history import History, PIN_KEYS
from autostart import set_enabled as set_autostart
from settings import Settings
from x11 import X11
from x11_clipboard import X11Clipboard
from search import snippet, visible_title
from paste_keys import PasteKeys
from color_swatch import rgba
from action_shortcuts import (action_shortcut_from_event, matches_action_shortcut,
                              validate_action_shortcuts)

TRAY_ICONS = {
    "clipboard": "edit-paste",
    "scissors": "edit-cut",
    "paperclip": "mail-attachment-symbolic",
    "copy": "edit-copy",
}


class RowCollection:
    """Present the fixed pin list and scrolling history as one ordered list."""

    def __init__(self, app):
        self.app = app

    def get_children(self):
        pins = self.app.pin_rows.get_children()
        history = self.app.history_rows.get_children()
        return pins + history if self.app.settings.get("pins_position") == "top" else history + pins

    def get_selected_row(self):
        return self.app.pin_rows.get_selected_row() or self.app.history_rows.get_selected_row()

    def select_row(self, row):
        if row is not None:
            row.get_parent().select_row(row)


class App:
    def __init__(self):
        self.settings = Settings()
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.history = History(data_home / "linuxxy" / "history.sqlite",
                               limit=self.settings.get("history_size"))
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard_handler = self.clipboard.connect("owner-change", self.on_clipboard_change)
        self.closed = False
        self.paused = self.settings.get("monitoring_paused")
        self.x11 = None
        self.rich_clipboard = None
        self.return_window = None
        self.ignore_own_change_until = 0
        self.preview_id = None
        self.preview_auto = False
        self.preview = None
        self.preview_entry_id = None
        self.preview_side = "right"
        self.preview_width = self.settings.get("preview_width")
        self.content_width = self.settings.get("popup_width")
        self.preview_divider_width = 7
        self.preview_drag = None
        self.preview_move_id = None
        self.preview_resize_id = None
        self.pending_popup_origin = None
        self.hover_poll_id = None
        self.last_pointer_position = None
        self.multi_selection = set()
        self.paste_stack = []
        self.paste_keys = None
        self.paste_advance_id = None
        self.shortcut_phase = "toggle"
        self.shortcut_poll_id = None
        self.application_info = None

        self.window = Gtk.Window(title="Linuxxy")
        self.window.set_default_size(self.content_width, 120)
        self.window.set_decorated(False)
        self.window.set_resizable(True)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.set_name("linuxxy-popup")
        self.window.connect("delete-event", self.hide_window)
        self.window.connect("key-press-event", self.on_key)
        self.install_style()
        self.popup_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.window.add(self.popup_layout)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_column = box
        box.set_border_width(7)
        box.set_size_request(self.content_width, -1)
        self.popup_layout.pack_start(box, False, False, 0)
        self.search_line = Gtk.Box(spacing=5)
        self.search_line.set_no_show_all(True)
        box.pack_start(self.search_line, False, False, 3)
        self.title_label = Gtk.Label(label="Linuxxy")
        self.title_label.set_name("linuxxy-title")
        self.title_label.set_no_show_all(True)
        self.title_handle = Gtk.EventBox()
        self.title_handle.set_no_show_all(True)
        self.title_handle.set_tooltip_text("Drag to move popup")
        self.title_handle.add(self.title_label)
        self.title_handle.connect("button-press-event", self.drag_title)
        self.search_line.pack_start(self.title_handle, False, False, 5)
        self.search = Gtk.SearchEntry()
        self.search.set_name("linuxxy-search")
        self.search.set_no_show_all(True)
        self.search.set_placeholder_text("Search clipboard history")
        self.search.connect("changed", self.search_changed)
        self.search.connect("key-press-event", self.search_key)
        self.search_line.pack_start(self.search, True, True, 0)
        self.preview_button = Gtk.Button()
        self.preview_button.set_name("linuxxy-preview-toggle")
        self.preview_button.set_image(Gtk.Image.new_from_icon_name(
            "view-sidebar-symbolic", Gtk.IconSize.MENU))
        self.preview_button.set_relief(Gtk.ReliefStyle.NONE)
        self.preview_button.set_can_focus(False)
        self.preview_button.set_tooltip_text("Open preview (Ctrl+Space)")
        self.preview_button.connect("clicked", lambda *_: self.toggle_preview())
        self.search_line.pack_end(self.preview_button, False, False, 2)
        self.preview_button.show_all()
        self.search_separator = Gtk.Separator()
        self.search_separator.set_no_show_all(True)
        box.pack_start(self.search_separator, False, False, 4)
        self.history_scroll = Gtk.ScrolledWindow()
        self.history_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(self.history_scroll, True, True, 0)
        self.pin_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.pin_container.set_no_show_all(True)
        box.pack_start(self.pin_container, False, False, 0)
        self.pin_separator = Gtk.Separator()
        self.pin_rows = self.make_list()
        self.pin_scroll = Gtk.ScrolledWindow()
        self.pin_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pin_scroll.add(self.pin_rows)
        self.history_rows = self.make_list()
        self.history_scroll.add(self.history_rows)
        self.rows = RowCollection(self)
        self.rebuilding_rows = False
        self.syncing_selection = False
        box.pack_start(Gtk.Separator(), False, False, 4)
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        footer.set_name("linuxxy-footer")
        footer.set_no_show_all(not self.settings.get("show_footer"))
        self.footer = footer
        box.pack_start(footer, False, False, 0)

        def footer_button(label, shortcut, callback):
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", callback)
            line = Gtk.Box(spacing=8)
            title = Gtk.Label(label=label, xalign=0)
            line.pack_start(title, True, True, 0)
            badge = Gtk.Label(label=shortcut, xalign=1)
            badge.set_name("linuxxy-footer-shortcut")
            line.pack_end(badge, False, False, 0)
            button.add(line)
            footer.pack_start(button, False, False, 0)
            return button

        self.queue_button = Gtk.Button(label="Queue")
        self.queue_button.set_relief(Gtk.ReliefStyle.NONE)
        self.queue_button.set_no_show_all(True)
        self.queue_button.set_tooltip_text("Copy selected items in order, then press Ctrl+V for each")
        self.queue_button.connect("clicked", self.start_paste_stack)
        footer.pack_start(self.queue_button, False, False, 0)
        self.clear_button = footer_button("Clear", "Ctrl+Alt+Delete", self.confirm_clear)
        self.preferences_button = footer_button("Preferences…", "Ctrl+,", self.show_settings)
        self.about_button = footer_button("About Linuxxy", "", self.show_about)
        self.quit_button = footer_button("Quit", "Ctrl+Q", self.quit)
        self.preview_divider = Gtk.EventBox()
        self.preview_divider.set_name("linuxxy-preview-divider")
        self.preview_divider.set_no_show_all(True)
        self.preview_divider.set_size_request(self.preview_divider_width, -1)
        self.preview_divider.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                                        Gdk.EventMask.POINTER_MOTION_MASK)
        self.preview_divider.connect("button-press-event", self.preview_drag_start)
        self.preview_divider.connect("motion-notify-event", self.preview_drag_motion)
        self.preview_divider.connect("button-release-event", self.preview_drag_end)
        self.preview_divider.connect("realize", self.preview_divider_realize)
        self.popup_layout.pack_start(self.preview_divider, False, False, 0)
        self.preview_divider.hide()
        self.preview_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.preview_pane.set_name("linuxxy-preview")
        self.preview_pane.set_no_show_all(True)
        self.preview_pane.set_size_request(self.preview_width, -1)
        self.popup_layout.pack_start(self.preview_pane, False, False, 0)
        preview_header = Gtk.Box(spacing=6)
        preview_header.set_border_width(7)
        self.preview_pane.pack_start(preview_header, False, False, 0)
        self.preview_heading = Gtk.Label(label="Preview", xalign=0)
        self.preview_heading.set_name("linuxxy-preview-heading")
        preview_header.pack_start(self.preview_heading, True, True, 0)
        close_preview = Gtk.Button(label="×")
        close_preview.set_relief(Gtk.ReliefStyle.NONE)
        close_preview.set_can_focus(False)
        close_preview.set_tooltip_text("Close preview")
        close_preview.connect("clicked", lambda *_: self.cancel_preview())
        preview_header.pack_end(close_preview, False, False, 0)
        self.preview_scroll = Gtk.ScrolledWindow()
        self.preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.preview_pane.pack_start(self.preview_scroll, True, True, 0)
        self.preview_metadata = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.preview_metadata.set_border_width(9)
        self.preview_pane.pack_end(self.preview_metadata, False, False, 0)
        self.preview_pane.hide()
        self.update_search_visibility()

        self.tray = Gtk.StatusIcon.new_from_icon_name("edit-paste")
        self.tray.connect("activate", lambda *_: self.toggle_window())
        self.tray.connect("popup-menu", self.tray_menu)
        self.update_tray()
        self.poll_id = GLib.timeout_add(self.settings.get("check_interval_ms"), self.poll_clipboard)
        self.last_signature = None
        if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
            try:
                self.rich_clipboard = X11Clipboard()
            except (RuntimeError, OSError) as error:
                print(f"Clipboard formats unavailable: {error}")
            try:
                self.x11 = X11(self.shortcut_pressed, self.settings.get("shortcut"))
            except (RuntimeError, OSError, ValueError) as error:
                print(f"Global shortcut unavailable: {error}")
        self.capture()
        self.refresh()

    def make_list(self):
        rows = Gtk.ListBox()
        rows.set_name("linuxxy-list")
        rows.set_selection_mode(Gtk.SelectionMode.SINGLE)
        rows.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        rows.connect("motion-notify-event", self.list_motion)
        rows.connect("row-activated", lambda _list, row: self.choose(row))
        rows.connect("row-selected", self.mark_selected)
        rows.connect("key-press-event", self.on_key)
        return rows

    def install_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            #linuxxy-popup { background: #28292d; border: 1px solid #4a4b50; border-radius: 9px; }
            #linuxxy-search { min-height: 30px; margin: 2px 2px 4px 2px; }
            #linuxxy-preview-toggle { min-width: 24px; padding: 0 2px; color: #b8b9bd; }
            #linuxxy-title { color: #b8b9bd; font-size: 12px; }
            #linuxxy-list, #linuxxy-list > row { background: transparent; }
            #linuxxy-list > row { min-height: 31px; border-radius: 5px; }
            #linuxxy-list > row label { color: #eeeeee; }
            box.linuxxy-selected { background-color: #466ca8; border-radius: 5px; color: white; }
            #linuxxy-footer button { min-height: 24px; padding: 1px 9px; font-size: 12px; color: #eee; }
            #linuxxy-footer button:hover { background: #3b3d43; border-radius: 5px; }
            #linuxxy-footer-shortcut { color: #a7a8ad; font-size: 10px; }
            #linuxxy-index { color: #aaa; font-size: 10px; min-width: 16px; }
            box.linuxxy-multi-selected { background-color: #4d624b; border-radius: 5px; color: white; }
            #linuxxy-color-swatch { border: 1px solid #888; border-radius: 2px; }
            #linuxxy-preview { background: #222327; border-left: 1px solid #4a4b50; }
            #linuxxy-preview.left { border-left: none; border-right: 1px solid #4a4b50; }
            #linuxxy-preview-divider { background: #34353a; }
            #linuxxy-preview-heading { color: #cccccc; font-size: 11px; }
            #linuxxy-preview button { color: #cccccc; }
            #linuxxy-preview-metadata { color: #b6b6ba; font-size: 11px; }
            #linuxxy-preview textview, #linuxxy-preview textview text {
                background: #222327; color: #eeeeee;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_clipboard_change(self, *_):
        GLib.idle_add(self.capture, time.monotonic() > self.ignore_own_change_until)

    def search_changed(self, *_):
        self.update_search_visibility()
        GLib.idle_add(self.refresh)

    def update_search_visibility(self):
        visible = self.settings.get("show_search_field") and (
            self.settings.get("search_visibility") == "always" or bool(self.search.get_text())
        )
        was_focused = self.search.is_focus()
        self.search.set_visible(visible)
        self.title_label.set_visible(self.settings.get("show_title"))
        self.title_handle.set_visible(self.settings.get("show_title"))
        header_visible = visible or self.settings.get("show_title")
        self.search_line.set_visible(header_visible)
        self.search_separator.set_visible(header_visible)
        if not visible and was_focused and self.window.get_visible():
            row = self.selected()
            if row:
                row.grab_focus()

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
            if signature != self.last_signature and self.paste_stack:
                self.cancel_paste_stack()
            self.last_signature = signature
            if not self.paused:
                source_app = self.x11.clipboard_source_app() if self.x11 else None
                if uris and self.settings.get("save_files"):
                    self.history.add_files(uris, source_app)
                elif image and signature and self.settings.get("save_images"):
                    self.history.add_image(data, source_app)
                elif html and text and self.settings.get("save_text"):
                    self.history.add_rich(text, html, source_app)
                elif text and self.settings.get("save_text"):
                    self.history.add(text, source_app)
                self.refresh()
        return False

    def source_icon(self, wm_class):
        if self.application_info is None:
            self.application_info = {}
            for app in Gio.AppInfo.get_all():
                desktop_id = app.get_id() or ""
                names = (app.get_startup_wm_class(), desktop_id.removesuffix(".desktop"))
                for name in names:
                    if name:
                        self.application_info.setdefault(name.casefold(), app)
        app = self.application_info.get(wm_class.casefold())
        icon = app.get_icon() if app else None
        if icon is None:
            icon = Gio.ThemedIcon.new("application-x-executable")
        return Gtk.Image.new_from_gicon(icon, Gtk.IconSize.MENU), app.get_name() if app else wm_class

    def refresh(self):
        selected = self.selected()
        selected_id = selected.entry_id if selected else None
        self.rebuilding_rows = True
        for listbox in (self.pin_rows, self.history_rows):
            for child in listbox.get_children():
                listbox.remove(child)
        restored = None
        row_count = 0
        image_count = 0
        pin_count = 0
        pin_image_count = 0
        for index, (entry_id, value, pinned, kind, data, pin_key, matches, shown, source_app) in enumerate(self.history.list(
            self.search.get_text(), self.settings.get("search_mode"),
            self.settings.get("pins_position"), self.settings.get("sort_by")
        )):
            row = Gtk.ListBoxRow()
            row.set_name("linuxxy-row")
            row.entry_id, row.value, row.pinned = entry_id, value, bool(pinned)
            row.kind, row.data = kind, data
            row.pin_key = pin_key
            row.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK |
                           Gdk.EventMask.POINTER_MOTION_MASK)
            row.connect("enter-notify-event", self.row_motion)
            row.connect("motion-notify-event", self.row_motion)
            row.connect("button-press-event", self.row_click)
            if kind == "image" and data:
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                scale = min(1, 340 / pixbuf.get_width(),
                            self.settings.get("image_max_height") / pixbuf.get_height())
                thumbnail = pixbuf.scale_simple(max(1, int(pixbuf.get_width() * scale)),
                                                max(1, int(pixbuf.get_height() * scale)),
                                                GdkPixbuf.InterpType.BILINEAR)
                visual = Gtk.Image.new_from_pixbuf(thumbnail)
                preview, visible_matches = snippet("Image", matches)
                row.display_title = "Image"
                image_count += 1
            else:
                visual = None
                title = shown
                if kind == "files" and shown == value:
                    title = value.rsplit(" ", 1)[0]
                display_title = visible_title(title, self.settings.get("show_special_symbols")) \
                    if kind in ("text", "rich") else title
                preview, visible_matches = snippet(display_title, matches)
                row.display_title = title
            label = Gtk.Label(label=preview, xalign=0)
            if visible_matches:
                tags = {
                    "bold": ("<b>", "</b>"),
                    "italic": ("<i>", "</i>"),
                    "underline": ("<u>", "</u>"),
                    "color": ('<span background="#e9c46a" foreground="#202020">', '</span>'),
                }
                opening, closing = tags[self.settings.get("highlight_match")]
                parts = []
                cursor = 0
                for left, right in visible_matches:
                    parts.append(GLib.markup_escape_text(preview[cursor:left]))
                    parts.append(opening + GLib.markup_escape_text(preview[left:right]) + closing)
                    cursor = right
                parts.append(GLib.markup_escape_text(preview[cursor:]))
                label.set_markup("".join(parts))
            label.set_ellipsize(3)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            content = Gtk.Box(spacing=8)
            content.set_border_width(4)
            row.content = content
            if source_app and self.settings.get("show_application_icons"):
                app_icon, app_name = self.source_icon(source_app)
                app_icon.set_pixel_size(15)
                app_icon.set_tooltip_text(f"Copied from {app_name}")
                content.pack_start(app_icon, False, False, 2)
            if pinned:
                content.pack_start(Gtk.Image.new_from_icon_name("emblem-favorite", Gtk.IconSize.MENU),
                                   False, False, 2)
            if kind == "files":
                content.pack_start(Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.MENU),
                                   False, False, 2)
            if kind in ("text", "rich") and self.settings.get("show_hex_color_swatch"):
                color = rgba(value)
                if color is not None:
                    swatch = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 14, 14)
                    swatch.fill(color)
                    swatch_box = Gtk.Box()
                    swatch_box.set_name("linuxxy-color-swatch")
                    swatch_box.set_valign(Gtk.Align.CENTER)
                    swatch_box.pack_start(Gtk.Image.new_from_pixbuf(swatch), False, False, 0)
                    content.pack_start(swatch_box, False, False, 2)
            if visual:
                content.pack_start(visual, False, False, 0)
            content.pack_start(label, True, True, 0)
            if pin_key or index < 9:
                badge = Gtk.Label(label=pin_key.upper() if pin_key else str(index + 1))
                badge.set_name("linuxxy-index")
                content.pack_end(badge, False, False, 4)
                if pin_key:
                    badge.set_tooltip_text(f"Ctrl+{pin_key.upper()} copy · Alt+{pin_key.upper()} paste")
            row.add(content)
            (self.pin_rows if pinned else self.history_rows).add(row)
            pin_count += bool(pinned)
            pin_image_count += bool(pinned and kind == "image")
            row_count += 1
            if entry_id == selected_id:
                restored = row
        for child in self.pin_container.get_children():
            self.pin_container.remove(child)
        if self.settings.get("pins_position") == "top":
            self.pin_container.pack_start(self.pin_scroll, False, False, 0)
            self.pin_container.pack_start(self.pin_separator, False, False, 4)
            self.main_column.reorder_child(self.pin_container, 2)
        else:
            self.pin_container.pack_start(self.pin_separator, False, False, 4)
            self.pin_container.pack_start(self.pin_scroll, False, False, 0)
            self.main_column.reorder_child(self.pin_container, 3)
        self.pin_separator.set_visible(pin_count > 0 and row_count > pin_count)
        self.pin_rows.show_all()
        self.pin_scroll.show()
        self.history_rows.show_all()
        if pin_count:
            self.pin_container.show()
        else:
            self.pin_container.hide()
        self.rebuilding_rows = False
        self.multi_selection.intersection_update(row.entry_id for row in self.rows.get_children())
        if restored:
            self.rows.select_row(restored)
        elif self.rows.get_children():
            self.rows.select_row(self.rows.get_children()[0])
        self.update_multi_selection()
        self.pin_count = pin_count
        self.pin_image_count = pin_image_count
        self.resize_popup(row_count, image_count)
        self.update_tray()

    def resize_popup(self, count, image_count=0):
        # Match the content instead of leaving a large empty window behind.
        visible = count
        image_extra = max(0, self.settings.get("image_max_height") - 30)
        height = 105 + max(34, visible * 40 + min(image_count, visible) * image_extra)
        if not self.search_line.get_visible():
            height -= 43
        elif not self.search.get_visible():
            height -= 14
        if self.settings.get("show_footer"):
            height += 89
        else:
            height -= 26
        display = Gdk.Display.get_default()
        _screen, pointer_x, pointer_y, _mods = display.get_pointer()
        monitor = (display.get_monitor_at_window(self.window.get_window())
                   if self.window.get_visible() else
                   display.get_monitor_at_point(pointer_x, pointer_y))
        monitor = self.popup_monitor(display, monitor)
        work = monitor.get_workarea()
        height_limit = min(self.settings.get("popup_max_height"), max(120, work.height - 20))
        pin_height = self.pin_count * 40 + self.pin_image_count * image_extra
        self.pin_scroll.set_size_request(-1, min(pin_height, max(40, int(height_limit * .4))))
        self.popup_size = (self.content_width, min(height, height_limit))
        if self.preview is not None:
            self.layout_preview()
        else:
            self.window.resize(*self.popup_size)

    def list_motion(self, _list, event):
        row = _list.get_row_at_y(int(event.y))
        if row is not None and self.window.get_visible() and self.selected() is not row:
            self.rows.select_row(row)
        return False

    def row_motion(self, row, _event):
        if self.window.get_visible() and self.selected() is not row:
            self.rows.select_row(row)
        return False

    def poll_hover(self):
        if not self.window.get_visible():
            self.hover_poll_id = None
            return False
        display = Gdk.Display.get_default()
        _screen, x, y, _mods = display.get_pointer()
        if (x, y) == self.last_pointer_position:
            return True
        self.last_pointer_position = (x, y)
        _ok, origin_x, origin_y = self.window.get_window().get_origin()
        local_x, local_y = x - origin_x, y - origin_y
        for listbox in (self.pin_rows, self.history_rows):
            if not listbox.get_visible() or not listbox.get_mapped():
                continue
            viewport = self.history_scroll if listbox is self.history_rows else self.pin_scroll
            viewport_point = viewport.translate_coordinates(self.window, 0, 0)
            if viewport_point is None:
                continue
            viewport_x, viewport_y = viewport_point
            if not (viewport_x <= local_x < viewport_x + viewport.get_allocated_width() and
                    viewport_y <= local_y < viewport_y + viewport.get_allocated_height()):
                continue
            point = listbox.translate_coordinates(self.window, 0, 0)
            if point is None:
                continue
            left, top = point
            if left <= local_x < left + listbox.get_allocated_width() and \
                    top <= local_y < top + listbox.get_allocated_height():
                row = listbox.get_row_at_y(local_y - top)
                if row is not None and row is not self.selected():
                    self.rows.select_row(row)
                break
        return True

    def row_click(self, row, event):
        if event.button == 1:
            if event.state & Gdk.ModifierType.CONTROL_MASK or (
                    event.state & Gdk.ModifierType.SHIFT_MASK and
                    not event.state & Gdk.ModifierType.MOD1_MASK):
                self.extend_selection(row, bool(event.state & Gdk.ModifierType.SHIFT_MASK))
                return True
            alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
            shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
            self.choose(row, paste=True if alt else None, plain=alt and shift)
            return True
        if event.button != 3:
            return False
        self.rows.select_row(row)
        menu = Gtk.Menu()
        actions = [("Paste", self.paste_selected),
                   ("Copy", self.copy_selected),
                   ("Remove from queue" if row.entry_id in self.multi_selection else "Add to queue",
                    lambda: self.extend_selection(row, False)),
                   ("Start paste queue", self.start_paste_stack),
                   ("Edit…", self.edit_selected),
                   ("Preview", self.show_preview),
                   ("Unpin" if row.pinned else "Pin", self.toggle_pin),
                   ("Delete", self.delete_selected)]
        if row.pinned and not self.search.get_text():
            actions.insert(-1, ("Move pin up", lambda: self.move_pin(-1)))
            actions.insert(-1, ("Move pin down", lambda: self.move_pin(1)))
        for label, callback in actions:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, fn=callback: fn())
            if label == "Start paste queue":
                item.set_sensitive(len(self.multi_selection) >= 2)
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def selected(self):
        return self.rows.get_selected_row()

    def mark_selected(self, _list, selected):
        if self.rebuilding_rows or self.syncing_selection:
            return
        if selected:
            self.syncing_selection = True
            (self.history_rows if _list is self.pin_rows else self.pin_rows).unselect_all()
            self.syncing_selection = False
        selected = self.selected()
        for row in self.rows.get_children():
            row.content.get_style_context().remove_class("linuxxy-selected")
        if selected:
            selected.content.get_style_context().add_class("linuxxy-selected")
        self.schedule_preview()

    def update_multi_selection(self):
        for row in self.rows.get_children():
            style = row.content.get_style_context()
            if row.entry_id in self.multi_selection:
                style.add_class("linuxxy-multi-selected")
            else:
                style.remove_class("linuxxy-multi-selected")
        self.queue_button.set_label(f"Queue {len(self.multi_selection)}")
        self.queue_button.set_visible(len(self.multi_selection) >= 2)

    def extend_selection(self, row, shift):
        rows = self.rows.get_children()
        if shift:
            anchor = self.selected() or row
            first, last = sorted((rows.index(anchor), rows.index(row)))
            self.multi_selection.update(item.entry_id for item in rows[first:last + 1])
        elif row.entry_id in self.multi_selection:
            self.multi_selection.remove(row.entry_id)
        else:
            self.multi_selection.add(row.entry_id)
        self.rows.select_row(row)
        row.grab_focus()
        self.update_multi_selection()

    def cancel_preview(self):
        if self.preview_resize_id is not None:
            GLib.source_remove(self.preview_resize_id)
            self.preview_resize_id = None
        if self.preview_id and GLib.MainContext.default().find_source_by_id(self.preview_id):
            GLib.source_remove(self.preview_id)
        self.preview_id = None
        if self.preview is not None:
            x, y = self.window.get_position()
            if self.preview_side == "left":
                x += self.preview_width + self.preview_divider_width
            self.preview_pane.hide()
            self.preview_divider.hide()
            self.preview_drag = None
            self.preview = None
            self.preview_auto = False
            self.preview_entry_id = None
            self.preview_button.set_tooltip_text("Open preview (Ctrl+Space)")
            self.window.resize(*self.popup_size)
            self.pending_popup_origin = (x, y)
            self.window.move(x, y)
            if self.preview_move_id is not None:
                GLib.source_remove(self.preview_move_id)
            self.preview_move_id = GLib.timeout_add(60, self.finish_preview_move)

    def finish_preview_move(self):
        if self.window.get_visible() and self.preview is None and self.pending_popup_origin:
            if self.window.get_size()[0] > self.content_width + 2:
                return True
            self.window.move(*self.pending_popup_origin)
        self.preview_move_id = None
        self.pending_popup_origin = None
        return False

    def schedule_preview(self):
        if self.preview_id and GLib.MainContext.default().find_source_by_id(self.preview_id):
            GLib.source_remove(self.preview_id)
        self.preview_id = None
        row = self.selected()
        if self.preview is not None:
            if row:
                self.render_preview_content(row)
            else:
                self.cancel_preview()
            return
        if (row and self.window.get_visible() and
                self.settings.get("open_preview_automatically")):
            self.preview_id = GLib.timeout_add(
                self.settings.get("preview_delay_ms"), self.show_automatic_preview, row.entry_id
            )

    def show_automatic_preview(self, entry_id):
        self.preview_id = None
        row = self.selected()
        if row and row.entry_id == entry_id and self.window.get_visible():
            self.show_preview(automatic=True)
        return False

    def choose(self, row, paste=None, plain=False, cancel_stack=True):
        self.cancel_preview()
        if cancel_stack:
            self.cancel_paste_stack()
        if paste is None:
            paste = self.settings.get("paste_by_default")
        self.copy_entry(row, self.settings.get("remove_formatting_by_default") != plain)
        self.reset_shortcut_cycle()
        self.remember_popup_position()
        self.window.hide()
        self.search.set_text("")
        self.multi_selection.clear()
        self.refresh()
        if paste and self.x11 and self.return_window:
            self.x11.activate(self.return_window)
            self.paste_attempts = 0
            GLib.timeout_add(50, self.delayed_paste)

    def copy_entry(self, row, plain=None):
        if plain is None:
            plain = self.settings.get("remove_formatting_by_default")
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
        self.update_tray()

    def start_paste_stack(self, *_):
        selected = [row for row in self.rows.get_children()
                    if row.entry_id in self.multi_selection]
        if len(selected) < 2:
            return
        self.cancel_paste_stack()
        try:
            if not self.paste_keys:
                self.paste_keys = PasteKeys(self.advance_paste_stack)
        except (RuntimeError, OSError, XError) as error:
            alert = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                      message_type=Gtk.MessageType.ERROR,
                                      buttons=Gtk.ButtonsType.CLOSE,
                                      text=f"Paste queue unavailable: {error}")
            alert.run()
            alert.destroy()
            return
        items = [(row.value, row.kind, row.data) for row in selected]
        self.choose(selected[0], paste=False, cancel_stack=False)
        self.paste_stack = items
        self.update_tray()

    def advance_paste_stack(self):
        if not self.paste_stack or self.paste_advance_id:
            return False
        # X11 paste targets may request the selection after the key release.
        self.paste_advance_id = GLib.timeout_add(250, self._finish_paste_advance)
        return False

    def _finish_paste_advance(self):
        self.paste_advance_id = None
        if not self.paste_stack:
            return False
        self.paste_stack.pop(0)
        if self.paste_stack:
            value, kind, data = self.paste_stack[0]
            self.copy_entry(SimpleNamespace(value=value, kind=kind, data=data))
            self.update_tray()
        else:
            self.cancel_paste_stack()
        return False

    def cancel_paste_stack(self):
        if self.paste_advance_id:
            GLib.source_remove(self.paste_advance_id)
            self.paste_advance_id = None
        self.paste_stack.clear()
        if self.paste_keys:
            self.paste_keys.close()
            self.paste_keys = None
        self.update_tray()

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

    def edit_selected(self, *_):
        row = self.selected()
        if not row:
            return
        current = self.history.get(row.entry_id)
        if current is None:
            self.refresh()
            return
        self.cancel_preview()
        editor = Gtk.Dialog(title="Edit clipboard item", transient_for=self.window,
                            flags=Gtk.DialogFlags.MODAL)
        editor.set_default_size(540, 390)
        editor.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save_button = editor.add_button("Save", Gtk.ResponseType.OK)
        save_button.get_style_context().add_class("suggested-action")
        editor.set_default_response(Gtk.ResponseType.OK)
        area = editor.get_content_area()
        area.set_border_width(14)
        area.set_spacing(10)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        area.pack_start(grid, False, False, 0)
        alias = Gtk.Entry()
        alias.set_hexpand(True)
        alias.set_placeholder_text("Shown in history (optional)")
        alias.set_text(current["alias"] or "")
        alias.set_sensitive(current["kind"] != "image")
        grid.attach(Gtk.Label(label="Alias", xalign=0), 0, 0, 1, 1)
        grid.attach(alias, 1, 0, 1, 1)
        pin_key = None
        if current["pinned"]:
            pin_key = Gtk.ComboBoxText()
            for key in self.history.available_pin_keys(row.entry_id):
                pin_key.append(key, key.upper())
            pin_key.set_active_id(current["pin_key"])
            grid.attach(Gtk.Label(label="Pin shortcut", xalign=0), 0, 1, 1, 1)
            grid.attach(pin_key, 1, 1, 1, 1)
        area.pack_start(Gtk.Label(label="Content", xalign=0), False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(190)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        area.pack_start(scroll, True, True, 0)
        content = Gtk.TextView()
        content.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        content.set_left_margin(8)
        content.set_right_margin(8)
        editable = current["kind"] in ("text", "rich")
        content.set_editable(editable)
        if current["kind"] == "image":
            initial_text = "Image content cannot be edited."
        elif current["kind"] == "files":
            initial_text = current["data"].decode("utf-8").replace("\r", "")
        else:
            initial_text = current["text"]
        content.get_buffer().set_text(initial_text)
        scroll.add(content)
        warning = None
        if current["kind"] == "rich":
            warning = Gtk.Label(label="Changing the content will remove its formatting.", xalign=0)
            warning.set_no_show_all(True)
            area.pack_start(warning, False, False, 0)

        def update_save(*_):
            start, end = content.get_buffer().get_bounds()
            content_changed = editable and (
                content.get_buffer().get_text(start, end, True) != current["text"]
            )
            alias_changed = (alias.get_text().strip() or None) != current["alias"]
            pin_changed = bool(pin_key and pin_key.get_active_id() != current["pin_key"])
            save_button.set_sensitive(alias_changed or content_changed or pin_changed)
            if warning:
                warning.set_visible(content_changed)

        alias.connect("changed", update_save)
        content.get_buffer().connect("changed", update_save)
        if pin_key:
            pin_key.connect("changed", update_save)
        saved = False
        editor.show_all()
        update_save()
        while editor.run() == Gtk.ResponseType.OK:
            start, end = content.get_buffer().get_bounds()
            new_content = content.get_buffer().get_text(start, end, True)
            try:
                self.history.edit(
                    row.entry_id, alias=alias.get_text(),
                    content=new_content if editable and new_content != current["text"] else None,
                    pin_key=pin_key.get_active_id() if pin_key else None,
                )
            except ValueError as error:
                alert = Gtk.MessageDialog(transient_for=editor, modal=True,
                                          message_type=Gtk.MessageType.ERROR,
                                          buttons=Gtk.ButtonsType.CLOSE, text=str(error))
                alert.run()
                alert.destroy()
                continue
            saved = True
            break
        editor.destroy()
        if saved:
            self.refresh()

    def toggle_pin(self, *_):
        if row := self.selected():
            self.history.pin(row.entry_id, not row.pinned)
            self.refresh()

    def move_pin(self, step):
        row = self.selected()
        if row and row.pinned and not self.search.get_text():
            self.history.move_pin(row.entry_id, step)
            self.refresh()

    def delete_selected(self, *_):
        if row := self.selected():
            self.history.delete(row.entry_id)
            self.refresh()

    def clear(self, *_):
        self.history.clear()
        self.clear_system_clipboard_if_enabled()
        self.cancel_paste_stack()
        self.refresh()
        self.hide_window()

    def confirm_clear(self, *_args, all_items=False):
        if self.settings.get("suppress_clear_confirmation"):
            if all_items:
                self.clear_all()
            else:
                self.clear()
            return
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                   message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.NONE,
                                   text=("Clear all clipboard history, including pinned items?"
                                         if all_items else "Clear unpinned clipboard history?"))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button("Clear all" if all_items else "Clear", Gtk.ResponseType.OK)
        confirm.get_style_context().add_class("destructive-action")
        remember = Gtk.CheckButton(label="Don't ask again")
        dialog.get_message_area().pack_start(remember, False, False, 4)

        def respond(window, response):
            suppress = remember.get_active()
            window.destroy()
            if response != Gtk.ResponseType.OK:
                return
            if suppress:
                self.settings.set("suppress_clear_confirmation", True)
            if all_items:
                self.clear_all()
            else:
                self.clear()

        dialog.connect("response", respond)
        dialog.show_all()

    def clear_all(self):
        self.history.clear_all()
        self.clear_system_clipboard_if_enabled()
        self.cancel_paste_stack()
        self.refresh()
        self.hide_window()

    def clear_system_clipboard_if_enabled(self):
        if self.settings.get("clear_system_clipboard"):
            self.ignore_own_change_until = time.monotonic() + 1
            self.clipboard.set_text("", -1)
            self.clipboard.store()
            self.last_signature = ("text", "")

    def on_key(self, _window, event):
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down) and not (ctrl or alt or shift) and \
                not self.search.is_focus():
            rows = self.rows.get_children()
            if rows:
                current = self.selected()
                index = rows.index(current) if current in rows else -1
                index = max(0, min(len(rows) - 1, index + (1 if event.keyval == Gdk.KEY_Down else -1)))
                self.rows.select_row(rows[index])
                rows[index].grab_focus()
            return True
        if not self.search.get_visible() and self.window.get_visible():
            if event.keyval == Gdk.KEY_BackSpace and self.search.get_text():
                self.search.set_text(self.search.get_text()[:-1])
                return True
            if not event.state & (Gdk.ModifierType.CONTROL_MASK |
                                  Gdk.ModifierType.MOD1_MASK |
                                  Gdk.ModifierType.MOD4_MASK):
                typed = event.string
                if typed and typed.isprintable() and (
                        not typed.isspace() or self.search.get_text()):
                    self.search.set_text(self.search.get_text() + typed)
                    if self.search.get_visible():
                        self.search.grab_focus()
                        self.search.set_position(-1)
                    return True
        if matches_action_shortcut(self.settings.get("pin_shortcut"), event):
            self.toggle_pin()
            return True
        if matches_action_shortcut(self.settings.get("delete_shortcut"), event):
            self.delete_selected()
            return True
        if matches_action_shortcut(self.settings.get("preview_shortcut"), event):
            self.toggle_preview()
            return True
        if event.keyval == Gdk.KEY_F2:
            self.edit_selected()
            return True
        if alt and event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            self.move_pin(-1 if event.keyval == Gdk.KEY_Up else 1)
            return True
        if shift and not ctrl and event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            rows = self.rows.get_children()
            selected = self.selected()
            if rows and selected:
                index = rows.index(selected) + (1 if event.keyval == Gdk.KEY_Down else -1)
                self.extend_selection(rows[max(0, min(len(rows) - 1, index))], True)
            return True
        if ctrl and shift and event.keyval == Gdk.KEY_Return:
            self.start_paste_stack()
            return True
        if ctrl or alt:
            digit = Gdk.keyval_name(event.keyval)
            if digit and digit in "123456789":
                rows = self.rows.get_children()
                if int(digit) <= len(rows):
                    self.choose(rows[int(digit) - 1], paste=alt)
                return True
            key = (digit or "").lower()
            if key:
                pinned = next((row for row in self.rows.get_children()
                               if row.pin_key == key), None)
                if pinned:
                    self.choose(pinned, paste=alt, plain=alt and shift)
                    return True
        if event.keyval == Gdk.KEY_comma and ctrl:
            self.show_settings()
            return True
        if event.keyval == Gdk.KEY_q and ctrl:
            self.quit()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.hide_window()
            return True
        if event.keyval == Gdk.KEY_Delete and ctrl and alt:
            self.confirm_clear(all_items=shift)
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
        if any(matches_action_shortcut(self.settings.get(name), event)
               for name in ("pin_shortcut", "delete_shortcut", "preview_shortcut")):
            return self.on_key(self.window, event)
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            key = (Gdk.keyval_name(event.keyval) or "").lower()
            if any(row.pin_key == key for row in self.rows.get_children()):
                return self.on_key(self.window, event)
        if event.keyval == Gdk.KEY_Return:
            return self.on_key(self.window, event)
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down) and event.state & Gdk.ModifierType.SHIFT_MASK:
            return self.on_key(self.window, event)
        if event.keyval == Gdk.KEY_Down:
            first = next(iter(self.rows.get_children()), None)
            if first:
                self.rows.select_row(first)
                first.grab_focus()
            return True
        return False

    def hide_window(self, *_):
        if self.hover_poll_id is not None:
            GLib.source_remove(self.hover_poll_id)
            self.hover_poll_id = None
        self.reset_shortcut_cycle()
        self.cancel_preview()
        self.remember_popup_position()
        self.window.hide()
        self.search.set_text("")
        return True

    def remember_popup_position(self):
        if self.window.get_visible():
            x, y = self.pending_popup_origin or self.window.get_position()
            if self.preview is not None and self.preview_side == "left":
                x += self.preview_width + self.preview_divider_width
            self.settings.set("popup_last_position", [x, y])

    def reset_shortcut_cycle(self):
        self.shortcut_phase = "toggle"
        if self.shortcut_poll_id is not None:
            GLib.source_remove(self.shortcut_poll_id)
            self.shortcut_poll_id = None

    def shortcut_pressed(self, event_time=Gdk.CURRENT_TIME):
        if not self.window.get_visible():
            self.toggle_window(event_time)
            self.shortcut_phase = "opening"
            self.shortcut_poll_id = GLib.timeout_add(25, self.poll_shortcut_modifiers)
        elif self.shortcut_phase in ("opening", "cycle") and self.x11 and \
                self.x11.modifiers_down():
            self.shortcut_phase = "cycle"
            rows = self.rows.get_children()
            if rows:
                selected = self.selected()
                index = rows.index(selected) if selected in rows else -1
                self.rows.select_row(rows[(index + 1) % len(rows)])
        else:
            self.hide_window()

    def poll_shortcut_modifiers(self):
        if not self.window.get_visible() or self.shortcut_phase not in ("opening", "cycle"):
            self.shortcut_phase = "toggle"
            self.shortcut_poll_id = None
            return False
        if self.x11 and self.x11.modifiers_down():
            return True
        phase = self.shortcut_phase
        self.shortcut_phase = "toggle"
        self.shortcut_poll_id = None
        if phase == "cycle":
            row = self.selected()
            if row:
                self.choose(row)
        return False

    def drag_title(self, _widget, event):
        if event.button == 1:
            self.window.begin_move_drag(event.button, int(event.x_root), int(event.y_root),
                                        event.time)
            return True
        return False

    def popup_monitor(self, display, fallback):
        if self.settings.get("popup_position") in ("screen_center", "last_position"):
            screen = self.settings.get("popup_screen")
            if 0 < screen <= display.get_n_monitors():
                return display.get_monitor(screen - 1)
        return fallback

    def position_popup(self):
        if self.preview_move_id is not None:
            GLib.source_remove(self.preview_move_id)
            self.preview_move_id = None
        self.pending_popup_origin = None
        display = Gdk.Display.get_default()
        _screen, pointer_x, pointer_y, _mods = display.get_pointer()
        mode = self.settings.get("popup_position")
        width, height = self.popup_size
        anchor_x, anchor_y = pointer_x, pointer_y
        x, y = pointer_x, pointer_y
        tray_rectangle = None
        if mode in ("active_window", "screen_center") and self.x11:
            bounds = self.x11.window_bounds(self.return_window)
            if bounds:
                anchor_x = bounds[0] + bounds[2] // 2
                anchor_y = bounds[1] + bounds[3] // 2
                if mode == "active_window":
                    x = anchor_x - width // 2
                    y = anchor_y - height // 2
        if mode == "status_icon":
            available, _screen, rectangle, _orientation = self.tray.get_geometry()
            if available and rectangle.width > 4 and rectangle.height > 4:
                tray_rectangle = rectangle
                anchor_x, anchor_y = rectangle.x, rectangle.y
                x, y = rectangle.x, rectangle.y + rectangle.height
        elif mode == "last_position" and self.settings.get("popup_last_position"):
            x, y = self.settings.get("popup_last_position")
            anchor_x, anchor_y = x, y
        fallback_point = (pointer_x, pointer_y) if mode == "last_position" else (anchor_x, anchor_y)
        monitor = self.popup_monitor(display, display.get_monitor_at_point(*fallback_point))
        work = monitor.get_workarea()
        if mode == "last_position" and self.settings.get("popup_last_position"):
            source = display.get_monitor_at_point(anchor_x, anchor_y).get_workarea()
            if source.x != work.x or source.y != work.y:
                source_width = max(1, source.width - width)
                source_height = max(1, source.height - height)
                x = work.x + round((anchor_x - source.x) *
                                   max(0, work.width - width) / source_width)
                y = work.y + round((anchor_y - source.y) *
                                   max(0, work.height - height) / source_height)
        elif mode == "last_position":
            x = work.x + (work.width - width) // 2
            y = work.y + round(work.height * .2)
        if tray_rectangle and y + height > work.y + work.height:
            y = tray_rectangle.y - height
        if mode == "screen_center":
            x = work.x + (work.width - width) // 2
            y = work.y + (work.height - height) // 2
        x = max(work.x, min(x, work.x + work.width - width))
        y = max(work.y, min(y, work.y + work.height - height))
        self.window.move(x, y)
        return x, y

    def toggle_window(self, event_time=Gdk.CURRENT_TIME):
        if self.window.get_visible():
            self.hide_window()
        else:
            if self.x11:
                self.return_window = self.x11.active_window()
            self.refresh()
            self.position_popup()
            self.window.show_all()
            self.window.present_with_time(event_time)
            display = Gdk.Display.get_default()
            _screen, x, y, _mods = display.get_pointer()
            self.last_pointer_position = (x, y)
            if self.hover_poll_id is None:
                self.hover_poll_id = GLib.timeout_add(60, self.poll_hover)
            if self.search.get_visible():
                self.search.grab_focus()
            elif self.selected():
                self.selected().grab_focus()
            self.schedule_preview()

    def tray_menu(self, _icon, button, activate_time):
        menu = Gtk.Menu()
        for label, callback in (("Open", self.toggle_window),
                                ("Cancel paste queue", self.cancel_paste_stack),
                                ("Preferences…", self.show_settings),
                                ("Resume monitoring" if self.paused else "Pause monitoring", self.toggle_pause),
                                ("About Linuxxy", self.show_about),
                                ("Quit", self.quit)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, fn=callback: fn())
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, self.tray, button, activate_time)

    def show_about(self, *_):
        if getattr(self, "about", None) and self.about.get_visible():
            self.about.present()
            return
        dialog = Gtk.AboutDialog(transient_for=self.window)
        dialog.set_program_name("Linuxxy")
        dialog.set_comments("An X11 clipboard manager inspired by Maccy")
        dialog.set_website("https://github.com/SummerXDsss/linuxxy")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.connect("response", lambda window, *_: window.destroy())
        dialog.connect("destroy", lambda *_: setattr(self, "about", None))
        self.about = dialog
        dialog.show_all()
        dialog.present()

    def show_settings(self, *_):
        if getattr(self, "preferences", None) and self.preferences.get_visible():
            self.preferences.present()
            return
        self.cancel_preview()
        self.reset_shortcut_cycle()
        self.remember_popup_position()
        self.window.hide()
        window = Gtk.Window(title="Linuxxy Preferences")
        window.set_default_size(500, 600)
        window.set_border_width(14)
        window.set_transient_for(self.window)
        window.set_keep_above(True)
        window.connect("destroy", lambda *_: setattr(self, "preferences", None))
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        window.add(layout)
        notebook = Gtk.Notebook()
        layout.pack_start(notebook, True, True, 0)
        grids = {}
        for title in ("General", "Storage", "Appearance", "Advanced"):
            grid = Gtk.Grid(column_spacing=16, row_spacing=14)
            grid.set_border_width(16)
            if title == "Appearance":
                scroller = Gtk.ScrolledWindow()
                scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                scroller.add_with_viewport(grid)
                notebook.append_page(scroller, Gtk.Label(label=title))
            else:
                notebook.append_page(grid, Gtk.Label(label=title))
            grids[title] = grid

        def field(grid, row, label, widget):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

        shortcut = Gtk.Entry(text=self.settings.get("shortcut"))
        shortcut.set_tooltip_text(
            "Example: Super+Shift+V. Hold modifiers and press V again to cycle; "
            "release them to choose."
        )
        field(grids["General"], 0, "Open shortcut", shortcut)

        def shortcut_recorder(setting):
            entry = Gtk.Entry(text=self.settings.get(setting))
            entry.set_editable(False)
            entry.set_width_chars(17)
            entry.set_placeholder_text("Click, then press keys")
            entry.set_tooltip_text("Click and press a shortcut. Use Clear to disable it.")

            def record(_entry, event):
                if event.keyval == Gdk.KEY_Escape:
                    return True
                if event.keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and not \
                        event.state & (Gdk.ModifierType.CONTROL_MASK |
                                       Gdk.ModifierType.MOD1_MASK |
                                       Gdk.ModifierType.MOD4_MASK):
                    return False
                try:
                    recorded = action_shortcut_from_event(event)
                except ValueError as error:
                    entry.set_tooltip_text(str(error))
                    return True
                if recorded is not None:
                    entry.set_text(recorded)
                    entry.set_tooltip_text("Click and press a shortcut. Use Clear to disable it.")
                return True

            entry.connect("key-press-event", record)
            clear = Gtk.Button(label="Clear")
            clear.connect("clicked", lambda *_: entry.set_text(""))
            control = Gtk.Box(spacing=5)
            control.pack_start(entry, True, True, 0)
            control.pack_start(clear, False, False, 0)
            return entry, control

        pin_shortcut, pin_control = shortcut_recorder("pin_shortcut")
        field(grids["General"], 1, "Pin item", pin_control)
        delete_shortcut, delete_control = shortcut_recorder("delete_shortcut")
        field(grids["General"], 2, "Delete item", delete_control)
        preview_shortcut, preview_control = shortcut_recorder("preview_shortcut")
        field(grids["General"], 3, "Preview item", preview_control)
        paste = Gtk.CheckButton(label="Paste by default (Alt+Enter reverses)")
        paste.set_active(self.settings.get("paste_by_default"))
        grids["General"].attach(paste, 0, 4, 2, 1)
        remove_formatting = Gtk.CheckButton(label="Remove formatting by default (Alt+Shift reverses)")
        remove_formatting.set_active(self.settings.get("remove_formatting_by_default"))
        grids["General"].attach(remove_formatting, 0, 5, 2, 1)
        search_mode = Gtk.ComboBoxText()
        for key, label in (("exact", "Exact"), ("fuzzy", "Fuzzy"),
                           ("regex", "Regular expression"), ("mixed", "Mixed")):
            search_mode.append(key, label)
        search_mode.set_active_id(self.settings.get("search_mode"))
        field(grids["General"], 6, "Search mode", search_mode)
        launch_at_login = Gtk.CheckButton(label="Launch at login")
        launch_at_login.set_active(self.settings.get("launch_at_login"))
        grids["General"].attach(launch_at_login, 0, 7, 2, 1)
        shortcut_hint = Gtk.Label(label="Click a shortcut field, then press keys. Letters and digits need Ctrl, Alt, or Super.")
        shortcut_hint.set_line_wrap(True)
        shortcut_hint.set_xalign(0)
        grids["General"].attach(shortcut_hint, 0, 8, 2, 1)

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
        storage_size = Gtk.Box(spacing=9)
        storage_size.pack_start(size, False, False, 0)
        storage_size.pack_start(Gtk.Label(label=GLib.format_size(self.history.disk_size())),
                                False, False, 0)
        field(grids["Storage"], 3, "History items", storage_size)
        interval = Gtk.SpinButton.new_with_range(100, 5000, 100)
        interval.set_value(self.settings.get("check_interval_ms"))
        field(grids["Storage"], 4, "Clipboard check (ms)", interval)
        sort_by = Gtk.ComboBoxText()
        for key, label in (("last_copied", "Last copied"),
                           ("first_copied", "First copied"),
                           ("most_copied", "Most copied")):
            sort_by.append(key, label)
        sort_by.set_active_id(self.settings.get("sort_by"))
        field(grids["Storage"], 5, "Sort by", sort_by)

        pins_position = Gtk.ComboBoxText()
        pins_position.append("top", "Top")
        pins_position.append("bottom", "Bottom")
        pins_position.set_active_id(self.settings.get("pins_position"))
        field(grids["Appearance"], 0, "Pinned items", pins_position)
        image_height = Gtk.SpinButton.new_with_range(1, 200, 1)
        image_height.set_value(self.settings.get("image_max_height"))
        field(grids["Appearance"], 1, "Image thumbnail height", image_height)
        position = Gtk.ComboBoxText()
        for key, label in (("cursor", "Near pointer"), ("status_icon", "At tray icon"),
                           ("active_window", "Center of active window"),
                           ("screen_center", "Center of screen"),
                           ("last_position", "Last position")):
            position.append(key, label)
        position.set_active_id(self.settings.get("popup_position"))
        position_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        position_line = Gtk.Box(spacing=8)
        position_line.pack_start(position, False, False, 0)
        reset_last_position = [False]
        reset_position = Gtk.Button(label="Reset last position")
        reset_position.set_name("linuxxy-reset-position-setting")
        reset_position.set_no_show_all(True)
        def reset_saved_position(*_):
            reset_last_position[0] = True
            reset_position.hide()
        reset_position.connect("clicked", reset_saved_position)
        position_line.pack_start(reset_position, False, False, 0)
        position_controls.pack_start(position_line, False, False, 0)
        screen_row = Gtk.Box(spacing=8)
        screen_row.set_no_show_all(True)
        screen_row.pack_start(Gtk.Label(label="Screen"), False, False, 0)
        screen_choice = Gtk.ComboBoxText()
        screen_choice.set_name("linuxxy-popup-screen-setting")
        screen_choice.append("0", "Active screen")
        display = Gdk.Display.get_default()
        for index in range(display.get_n_monitors()):
            geometry = display.get_monitor(index).get_geometry()
            screen_choice.append(str(index + 1),
                                 f"Screen {index + 1} ({geometry.width}×{geometry.height})")
        saved_screen = self.settings.get("popup_screen")
        if saved_screen > display.get_n_monitors():
            screen_choice.append(str(saved_screen), f"Screen {saved_screen} (disconnected)")
        screen_choice.set_active_id(str(saved_screen))
        screen_row.pack_start(screen_choice, False, False, 0)
        position_controls.pack_start(screen_row, False, False, 0)

        def update_position_controls(*_):
            mode = position.get_active_id()
            if display.get_n_monitors() > 1 and mode in ("screen_center", "last_position"):
                for child in screen_row.get_children():
                    child.show_all()
                screen_row.show()
            else:
                screen_row.hide()
            reset_position.set_visible(mode == "last_position" and
                                       self.settings.get("popup_last_position") is not None and
                                       not reset_last_position[0])

        position.connect("changed", update_position_controls)
        update_position_controls()
        field(grids["Appearance"], 2, "Open popup", position_controls)
        show_footer = Gtk.CheckButton(label="Show footer")
        show_footer.set_active(self.settings.get("show_footer"))
        grids["Appearance"].attach(show_footer, 0, 3, 2, 1)
        auto_preview = Gtk.CheckButton(label="Open preview automatically")
        auto_preview.set_active(self.settings.get("open_preview_automatically"))
        grids["Appearance"].attach(auto_preview, 0, 4, 2, 1)
        preview_delay = Gtk.SpinButton.new_with_range(200, 100000, 100)
        preview_delay.set_value(self.settings.get("preview_delay_ms"))
        preview_delay.set_sensitive(auto_preview.get_active())
        auto_preview.connect("toggled", lambda button: preview_delay.set_sensitive(button.get_active()))
        field(grids["Appearance"], 5, "Preview delay (ms)", preview_delay)
        highlight_match = Gtk.ComboBoxText()
        for key, name in (("bold", "Bold"), ("italic", "Italic"),
                          ("underline", "Underline"), ("color", "Color")):
            highlight_match.append(key, name)
        highlight_match.set_active_id(self.settings.get("highlight_match"))
        field(grids["Appearance"], 6, "Highlight matches", highlight_match)
        color_swatch = Gtk.CheckButton(label="Show color swatches for hex colors")
        color_swatch.set_active(self.settings.get("show_hex_color_swatch"))
        grids["Appearance"].attach(color_swatch, 0, 7, 2, 1)
        special_symbols = Gtk.CheckButton(label="Show spaces, tabs, and line breaks")
        special_symbols.set_active(self.settings.get("show_special_symbols"))
        grids["Appearance"].attach(special_symbols, 0, 8, 2, 1)
        search_display = Gtk.Box(spacing=8)
        show_search = Gtk.CheckButton(label="Show search field")
        show_search.set_active(self.settings.get("show_search_field"))
        search_display.pack_start(show_search, False, False, 0)
        search_visibility = Gtk.ComboBoxText()
        search_visibility.append("always", "Always")
        search_visibility.append("during_search", "While typing")
        search_visibility.set_active_id(self.settings.get("search_visibility"))
        search_visibility.set_sensitive(show_search.get_active())
        show_search.connect("toggled", lambda button: search_visibility.set_sensitive(button.get_active()))
        search_display.pack_start(search_visibility, False, False, 0)
        grids["Appearance"].attach(search_display, 0, 9, 2, 1)
        application_icons = Gtk.CheckButton(label="Show source application icons")
        application_icons.set_active(self.settings.get("show_application_icons"))
        grids["Appearance"].attach(application_icons, 0, 10, 2, 1)
        show_title = Gtk.CheckButton(label="Show title before search field")
        show_title.set_active(self.settings.get("show_title"))
        grids["Appearance"].attach(show_title, 0, 11, 2, 1)
        popup_width = Gtk.SpinButton.new_with_range(320, 1000, 10)
        popup_width.set_name("linuxxy-popup-width-setting")
        popup_width.set_value(self.settings.get("popup_width"))
        popup_height = Gtk.SpinButton.new_with_range(180, 2000, 10)
        popup_height.set_name("linuxxy-popup-height-setting")
        popup_height.set_value(self.settings.get("popup_max_height"))
        window_size = Gtk.Box(spacing=8)
        window_size.pack_start(Gtk.Label(label="Popup width"), False, False, 0)
        window_size.pack_start(popup_width, False, False, 0)
        window_size.pack_start(Gtk.Label(label="Height limit"), False, False, 0)
        window_size.pack_start(popup_height, False, False, 0)
        grids["Appearance"].attach(window_size, 0, 12, 2, 1)
        show_tray = Gtk.CheckButton(label="Show tray icon")
        show_tray.set_name("linuxxy-show-tray-setting")
        show_tray.set_active(self.settings.get("show_tray_icon"))
        tray_icon = Gtk.ComboBoxText()
        tray_icon.set_name("linuxxy-tray-icon-setting")
        for key, label in (("clipboard", "Clipboard"), ("scissors", "Scissors"),
                           ("paperclip", "Paperclip"), ("copy", "Copy")):
            tray_icon.append(key, label)
        tray_icon.set_active_id(self.settings.get("tray_icon"))
        tray_icon.set_sensitive(show_tray.get_active())
        show_tray.connect("toggled", lambda button: tray_icon.set_sensitive(button.get_active()))
        tray_controls = Gtk.Box(spacing=8)
        tray_controls.pack_start(show_tray, False, False, 0)
        tray_controls.pack_start(tray_icon, False, False, 0)
        grids["Appearance"].attach(tray_controls, 0, 13, 2, 1)
        show_recent = Gtk.CheckButton(label="Show recent copy in tray tooltip")
        show_recent.set_name("linuxxy-tray-recent-setting")
        show_recent.set_active(self.settings.get("show_recent_copy_in_tray"))
        grids["Appearance"].attach(show_recent, 0, 14, 2, 1)
        pause_monitoring = Gtk.CheckButton(label="Pause clipboard monitoring")
        pause_monitoring.set_name("linuxxy-pause-monitoring-setting")
        pause_monitoring.set_active(self.settings.get("monitoring_paused"))
        grids["Advanced"].attach(pause_monitoring, 0, 0, 2, 1)
        clear_on_quit = Gtk.CheckButton(label="Clear unpinned history on quit")
        clear_on_quit.set_name("linuxxy-clear-on-quit-setting")
        clear_on_quit.set_active(self.settings.get("clear_on_quit"))
        grids["Advanced"].attach(clear_on_quit, 0, 1, 2, 1)
        clear_system_clipboard = Gtk.CheckButton(label="Also clear system clipboard when clearing history")
        clear_system_clipboard.set_name("linuxxy-clear-clipboard-setting")
        clear_system_clipboard.set_active(self.settings.get("clear_system_clipboard"))
        grids["Advanced"].attach(clear_system_clipboard, 0, 2, 2, 1)
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
                validate_action_shortcuts(new_shortcut,
                                          (pin_shortcut.get_text(), delete_shortcut.get_text(),
                                           preview_shortcut.get_text()), PIN_KEYS)
                if self.x11 and new_shortcut != self.settings.get("shortcut"):
                    new_x11 = X11(self.shortcut_pressed, new_shortcut)
                elif not self.x11 and os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
                    new_x11 = X11(self.shortcut_pressed, new_shortcut)
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
                ("pin_shortcut", pin_shortcut.get_text()),
                ("delete_shortcut", delete_shortcut.get_text()),
                ("preview_shortcut", preview_shortcut.get_text()),
                ("paste_by_default", paste.get_active()),
                ("remove_formatting_by_default", remove_formatting.get_active()),
                ("history_size", size.get_value_as_int()),
                ("save_text", save_text.get_active()),
                ("save_images", save_images.get_active()),
                ("save_files", save_files.get_active()),
                ("check_interval_ms", interval.get_value_as_int()),
                ("search_mode", search_mode.get_active_id()),
                ("sort_by", sort_by.get_active_id()),
                ("pins_position", pins_position.get_active_id()),
                ("popup_position", position.get_active_id()),
                ("popup_screen", int(screen_choice.get_active_id())),
                ("popup_width", popup_width.get_value_as_int()),
                ("popup_max_height", popup_height.get_value_as_int()),
                ("show_footer", show_footer.get_active()),
                ("open_preview_automatically", auto_preview.get_active()),
                ("preview_delay_ms", preview_delay.get_value_as_int()),
                ("highlight_match", highlight_match.get_active_id()),
                ("image_max_height", image_height.get_value_as_int()),
                ("show_hex_color_swatch", color_swatch.get_active()),
                ("show_special_symbols", special_symbols.get_active()),
                ("show_search_field", show_search.get_active()),
                ("show_application_icons", application_icons.get_active()),
                ("show_title", show_title.get_active()),
                ("show_tray_icon", show_tray.get_active()),
                ("tray_icon", tray_icon.get_active_id()),
                ("show_recent_copy_in_tray", show_recent.get_active()),
                ("search_visibility", search_visibility.get_active_id()),
                ("clear_on_quit", clear_on_quit.get_active()),
                ("clear_system_clipboard", clear_system_clipboard.get_active()),
                ("monitoring_paused", pause_monitoring.get_active()),
                ("launch_at_login", launch_at_login.get_active()),
            ):
                self.settings.set(key, value, save=False)
            if reset_last_position[0]:
                self.settings.set("popup_last_position", None, save=False)
            self.settings.save()
            self.paused = self.settings.get("monitoring_paused")
            self.update_tray()
            self.content_width = self.settings.get("popup_width")
            self.main_column.set_size_request(self.content_width, -1)
            set_autostart(self.settings.get("launch_at_login"))
            self.history.set_limit(self.settings.get("history_size"))
            self.footer.set_no_show_all(not self.settings.get("show_footer"))
            self.footer.set_visible(self.settings.get("show_footer"))
            GLib.source_remove(self.poll_id)
            self.poll_id = GLib.timeout_add(self.settings.get("check_interval_ms"), self.poll_clipboard)
            self.update_search_visibility()
            self.refresh()
            window.destroy()

        save.connect("clicked", apply)
        self.preferences = window
        window.show_all()
        update_position_controls()
        window.present()

    def toggle_pause(self):
        self.paused = not self.paused
        self.settings.set("monitoring_paused", self.paused)
        self.update_tray()

    def update_tray(self):
        self.tray.set_visible(self.settings.get("show_tray_icon"))
        icon = TRAY_ICONS[self.settings.get("tray_icon")]
        if not Gtk.IconTheme.get_default().has_icon(icon):
            icon = "edit-paste"
        self.tray.set_from_icon_name(icon)
        status = "Linuxxy"
        if self.paused:
            status += " (paused)"
        if self.paste_stack:
            status += f" ({len(self.paste_stack)} items in paste queue)"
        recent = ""
        if self.settings.get("show_recent_copy_in_tray"):
            recent = " ".join(self.history.latest_unpinned_title().split())[:30]
            if recent:
                status += f" · {recent}"
        self.tray.set_title(recent)
        self.tray.set_tooltip_text(status)

    def toggle_preview(self):
        if self.preview is not None:
            self.cancel_preview()
        elif self.selected():
            self.show_preview()

    def show_preview(self, automatic=False):
        row = self.selected()
        if not row:
            return
        if self.preview_id and GLib.MainContext.default().find_source_by_id(self.preview_id):
            GLib.source_remove(self.preview_id)
        self.preview_id = None
        self.preview = self.preview_pane
        self.preview_auto = automatic
        self.render_preview_content(row)
        self.layout_preview()

    def render_preview_content(self, row):
        self.preview_entry_id = row.entry_id
        self.preview_heading.set_text("Image" if row.kind == "image" else
                                      "Files" if row.kind == "files" else "Preview")
        old = self.preview_scroll.get_child()
        if old is not None:
            self.preview_scroll.remove(old)
        pixbuf = None
        if row.kind == "image":
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(row.data)
            loader.close()
            pixbuf = loader.get_pixbuf()
        for child in self.preview_metadata.get_children():
            self.preview_metadata.remove(child)
        self.preview_metadata.pack_start(Gtk.Separator(), False, False, 3)
        metadata = self.history.metadata(row.entry_id)
        if metadata:
            def detail(label, value):
                line = Gtk.Label(label=f"{label}: {value}", xalign=0)
                line.set_name("linuxxy-preview-metadata")
                line.set_ellipsize(3)
                self.preview_metadata.pack_start(line, False, False, 0)

            if metadata["source_app"]:
                detail("Application", metadata["source_app"])
            if row.kind == "image":
                detail("Dimensions", f"{pixbuf.get_width()}×{pixbuf.get_height()}")
                detail("Size", GLib.format_size(len(row.data)))
            for label, key in (("First copied", "first_copied_at"),
                               ("Last copied", "copied_at")):
                if metadata[key]:
                    detail(label, datetime.fromtimestamp(metadata[key]).strftime("%Y-%m-%d %H:%M"))
            detail("Copies", metadata["copy_count"])
        self.preview_metadata.show_all()
        preview_text = (row.data.decode("utf-8").replace("\r", "")
                        if row.kind == "files" else row.value)
        if row.kind == "image":
            scale = min(1, 340 / pixbuf.get_width(), 390 / pixbuf.get_height())
            if scale < 1:
                pixbuf = pixbuf.scale_simple(max(1, int(pixbuf.get_width() * scale)),
                                             max(1, int(pixbuf.get_height() * scale)),
                                             GdkPixbuf.InterpType.BILINEAR)
            visual = Gtk.Image.new_from_pixbuf(pixbuf)
            visual.set_margin_top(10)
            self.preview_scroll.add_with_viewport(visual)
        else:
            text = Gtk.TextView()
            text.set_editable(False)
            text.set_can_focus(False)
            text.set_cursor_visible(False)
            text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            text.set_monospace(True)
            text.set_left_margin(12)
            text.set_right_margin(12)
            text.set_top_margin(9)
            text.get_buffer().set_text(preview_text)
            self.preview_scroll.add(text)
        self.preview_scroll.get_child().show_all()

    def layout_preview(self):
        if self.preview is None:
            return
        x, y = self.window.get_position()
        if not self.preview_pane.get_visible() and self.pending_popup_origin:
            x, y = self.pending_popup_origin
            self.pending_popup_origin = None
            if self.preview_move_id is not None:
                GLib.source_remove(self.preview_move_id)
                self.preview_move_id = None
        elif self.preview_pane.get_visible() and self.preview_side == "left":
            x += self.preview_width + self.preview_divider_width
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_point(x + self.content_width // 2, y)
        work = monitor.get_workarea()
        width = min(self.settings.get("preview_width"),
                    max(1, work.width - self.content_width - self.preview_divider_width))
        right_space = work.x + work.width - x - self.content_width
        left_space = x - work.x
        if right_space >= width + self.preview_divider_width or right_space >= left_space:
            side = "right"
            origin = min(x, work.x + work.width - self.content_width - width - self.preview_divider_width)
        else:
            side = "left"
            origin = max(work.x, x - width - self.preview_divider_width)
        origin = max(work.x, origin)
        self.preview_side = side
        self.preview_width = width
        self.preview_button.set_tooltip_text("Close preview (Ctrl+Space)")
        style = self.preview_pane.get_style_context()
        if side == "left":
            style.add_class("left")
        else:
            style.remove_class("left")
        if side == "left":
            self.popup_layout.reorder_child(self.preview_pane, 0)
            self.popup_layout.reorder_child(self.preview_divider, 1)
            self.popup_layout.reorder_child(self.main_column, 2)
        else:
            self.popup_layout.reorder_child(self.main_column, 0)
            self.popup_layout.reorder_child(self.preview_divider, 1)
            self.popup_layout.reorder_child(self.preview_pane, 2)
        self.preview_pane.set_size_request(width, -1)
        for child in self.preview_pane.get_children():
            child.show_all()
        self.preview_pane.show()
        self.preview_divider.show()
        self.window.queue_resize()
        self.window.resize(self.content_width + self.preview_divider_width + width,
                           max(self.popup_size[1], 360))
        if self.preview_resize_id is not None:
            GLib.source_remove(self.preview_resize_id)
        self.preview_resize_id = GLib.timeout_add(200, self.finish_preview_resize)
        self.window.move(origin, y)

    def finish_preview_resize(self):
        self.preview_resize_id = None
        if self.preview is not None:
            self.window.queue_resize()
            self.window.resize(self.content_width + self.preview_divider_width + self.preview_width,
                               max(self.popup_size[1], 360))
        return False

    def preview_divider_realize(self, widget):
        widget.get_window().set_cursor(Gdk.Cursor.new(Gdk.CursorType.SB_H_DOUBLE_ARROW))

    def preview_drag_start(self, _widget, event):
        if event.button != 1 or self.preview is None:
            return False
        self.preview_drag = (event.x_root, self.preview_width, self.content_width)
        return True

    def preview_drag_motion(self, _widget, event):
        if self.preview_drag is None:
            return False
        start_x, start_width, start_content_width = self.preview_drag
        delta = event.x_root - start_x
        desired = round(start_width + (delta if self.preview_side == "left" else -delta))
        total = start_width + start_content_width
        width = max(200, min(desired, 800, total - 320))
        if width == self.preview_width:
            return True
        self.preview_width = width
        self.content_width = total - width
        self.main_column.set_size_request(self.content_width, -1)
        self.preview_pane.set_size_request(width, -1)
        self.popup_size = (self.content_width, self.popup_size[1])
        return True

    def preview_drag_end(self, _widget, event):
        if event.button != 1 or self.preview_drag is None:
            return False
        self.preview_drag_motion(_widget, event)
        self.preview_drag = None
        if 200 <= self.preview_width <= 800:
            self.settings.set("preview_width", self.preview_width)
            self.settings.set("popup_width", self.content_width)
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.reset_shortcut_cycle()
        self.remember_popup_position()
        self.cancel_preview()
        self.cancel_paste_stack()
        self.clipboard.disconnect(self.clipboard_handler)
        if GLib.MainContext.default().find_source_by_id(self.poll_id):
            GLib.source_remove(self.poll_id)
        if self.settings.get("clear_on_quit"):
            self.history.clear()
            self.clear_system_clipboard_if_enabled()
        if self.x11:
            self.x11.close()
        if self.rich_clipboard:
            self.rich_clipboard.store()
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
