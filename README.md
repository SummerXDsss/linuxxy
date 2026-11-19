# Linuxxy

A lightweight, keyboard-first clipboard manager for Linux X11 desktops, inspired
by [Maccy](https://github.com/p0deje/Maccy).

## Requirements

- Linux desktop using X11; a system tray is recommended
- Python 3
- GTK 3 and PyGObject (`python3-gi` on Debian/Ubuntu)
- python-xlib (`python3-xlib` on Debian/Ubuntu)
- XTEST and RECORD X11 extensions (normally installed with Xorg)

On Debian/Ubuntu, install the Python dependencies with:

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 python3-xlib
```

## Install

```sh
python3 install.py
```

Linuxxy then appears in the app menu. Installation stays in `~/.local` and
does not require administrator access. To remove the application, run
`python3 ~/.local/share/linuxxy/install.py --uninstall`; your history and
preferences are kept.

## Run from source

```sh
python3 linuxxy.py
```

The process stays in the tray when the tray icon is enabled. A second instance
exits rather than opening a second clipboard watcher. Use the tray menu to pause
monitoring or quit. If the icon is hidden, the global shortcut still opens the
popup and Preferences remain available there.

## Use

1. Copy text, an image, or files in any application.
2. Press **Super+Shift+V** or click the tray icon.
   While holding Super+Shift, press **V** again to move to the next item;
   release the modifiers to copy the highlighted item. A single press leaves
   the popup open for searching.
3. Type to search. Press **Down** to focus results, then use arrow keys, or
   move the pointer over a result to highlight it.
4. Press **Enter** or click a result to copy it. Press **Alt+Enter** or
   **Alt+click** to paste it into the previous window. **Escape** hides the window.
   Use **Alt+Shift+Enter** or **Alt+Shift+click** to reverse the saved formatting
   preference for that paste (plain text by default).

Use **Ctrl+1…9** to copy a visible result or **Alt+1…9** to paste it.
Pinned entries get persistent letter shortcuts: **Ctrl+letter** copies,
**Alt+letter** pastes, and **Alt+Shift+letter** pastes plain text.
Click a row to choose it,
or right-click for Paste, Copy, Preview, Pin, and Delete. You can also use
**Alt+P** to pin and **Alt+Delete** to delete the selected entry. These shortcuts
can be changed or cleared in General settings.
Pinned entries can be moved with **Alt+Up/Down** or the right-click menu;
their letter shortcuts stay with each entry.
Pinned entries stay visible above or below the scrolling history, as chosen in
Appearance settings. If many items are pinned, their section scrolls within the
popup height limit. Arrow keys and Shift+arrow keys move across both sections.
Press **F2** or choose **Edit…** from the right-click menu to change an item's
display name, text content, or pinned letter shortcut. Changing formatted text
content converts that item to plain text; changing only its display name keeps
the original formatting.
Use **Ctrl+click** to select several results, or focus a result and press
**Shift+Up/Down** to extend the selection. Click **Queue N** or press
**Ctrl+Shift+Enter** to start a paste queue. The first item is copied; each
subsequent **Ctrl+V** pastes the current item and prepares the next one.
You can also add entries to the queue from the right-click menu. Choosing
another item or copying new content cancels the queue.
Use **Ctrl+Alt+Delete** to clear unpinned history or **Ctrl+Alt+Shift+Delete**
to clear all history, including pinned entries. The popup footer has menu-style
rows for Clear, Preferences, About, and Quit; **Ctrl+Q** also quits. Clearing
history asks for confirmation unless you choose **Don't ask again** in the dialog.
Press **Ctrl+Space** or click the sidebar button beside search to open or close
a selected result's full text or image
preview beside the list. The preview follows the selected item and opens on the
side with room. It shows the source application when known, copy times and count,
and image dimensions and size. This shortcut is configurable. The side preview
also opens after the selected item rests for 1.5 seconds by default. Drag the
divider between the list and preview to resize them; both widths are remembered.
Open **Preferences…** from the footer or tray menu, or press **Ctrl+,** while
the popup is open. General, Storage, Appearance, and Advanced pages cover the opening
shortcut, item pin/delete/preview shortcuts, default paste and formatting behavior,
text/image/file capture, history
limit, clipboard check interval, history sorting (last copied, first copied, or most copied),
search mode (exact, fuzzy, regex, or mixed), match highlighting (bold, italic,
underline, or color), pinned item position, popup position (pointer, tray icon,
active window, screen center, or last position), automatic preview
and its delay, image thumbnail height, hex color swatches, visible whitespace
symbols, search field visibility (always, while typing, or hidden), footer
visibility, an optional title before the search field, optional source application
icons, popup width and height limit, clear-on-quit behavior, optional system
clipboard clearing when history is cleared, pause monitoring, and launch
at login. When the search field is hidden, typing still filters the history;
Backspace removes the last character.
The tray icon can be hidden or changed to a clipboard, scissors, paperclip, or
copy symbol. An option puts the latest unpinned item in its tooltip and status
title; whether a tray host shows title text next to the icon depends on the desktop.
Storage shows the current history database size. Clearing history on quit keeps
pinned items; the separate clear-all shortcut removes them.
Drag the popup's title to move it; the last-position option reopens it there.
Preferences are saved in
`$XDG_CONFIG_HOME/linuxxy/settings.json`.
Source icons use the copying window's X11 application class and the matching
installed desktop icon. If the desktop does not identify the copying application,
the history item has no source icon.
Enabling launch at login creates `$XDG_CONFIG_HOME/autostart/linuxxy.desktop`.

History is stored in an unencrypted SQLite database at
`$XDG_DATA_HOME/linuxxy/history.sqlite`, usually
`~/.local/share/linuxxy/history.sqlite`. The current version handles plain
text, HTML alongside text, images, and file URI lists. Global shortcuts,
automatic paste, and restoring rich formats require X11. Wayland support is
future work. Large HTML and file lists use X11 incremental transfer. When the
desktop provides a clipboard manager, Linuxxy hands off selected rich or file
content on exit so it remains available to paste.

## License

Linuxxy is MIT licensed; see [LICENSE](LICENSE). Maccy's original MIT license
and copyright notice are preserved in [LICENSE-Maccy](LICENSE-Maccy).

## Desktop test

The [UI smoke test](tests/ui_smoke.py) starts Linuxxy and a separate GTK paste
target, sends real X11 keyboard shortcuts, and saves screenshots of the popup,
preview, preferences, desktop, and pasted result to [screenshots](screenshots). The
[visual sample](tests/visual_sample.py) renders the popup and all three settings
pages with known sample data. These scripts need `wmctrl`, `xwd`, and `ffmpeg`
in addition to the runtime dependencies. Run the smoke test from an X11
desktop when no other application has an active keyboard grab.
The [format smoke test](tests/formats_smoke.py) verifies small and large HTML
and file copying between separate X11 applications, checks content after exit
when a clipboard manager is present, and restores the clipboard afterward.
The [paste queue test](tests/paste_stack_smoke.py) selects three results in the
real popup and verifies their order through three actual Ctrl+V pastes.
The [editor UI test](tests/editor_ui_smoke.py) opens a real item editor and saves
screenshots before and after changing its display name, content, and pin shortcut.
The [editor data test](tests/editor_behavior.py) checks persistence, searching by
alias or content, rich-text conversion, and duplicate rejection.
The [search visibility test](tests/search_visibility_smoke.py) opens the real
popup in both hidden-field modes and searches with keyboard input.
The [history test](tests/history_behavior.py) verifies migration of older data,
copy counts, sorting, and pin order.
The [application icon test](tests/app_icon_smoke.py) copies from a real X11 window,
checks its saved source, and captures the popup with the matching desktop icon.
The [popup position test](tests/popup_position_smoke.py) measures and captures
the popup at each position in a real X11 session. Without a tray host, the tray
position falls back to the pointer.
The [shortcut cycle test](tests/shortcut_cycle_smoke.py) exercises held modifiers,
repeated opening-key presses, and selection on release with real X11 events.
The [action shortcut test](tests/action_shortcuts_smoke.py) records new pin,
delete, and preview keys in the real settings window and uses them in the popup.
The [preview slideout test](tests/preview_slideout_smoke.py) captures text and
image previews on both sides of the popup and verifies metadata and live
selection updates, including pointer hover. It also drags the divider with X11
mouse events and checks saved widths.
The [window size test](tests/window_size_smoke.py) changes width and height in
Appearance settings, reopens a long history, and captures the resized popup.
The [Advanced settings test](tests/advanced_settings_smoke.py) changes the real
settings controls, checks paused monitoring and clipboard clearing, and verifies
that pinned items survive clear-on-quit.
The [tray settings test](tests/tray_settings_smoke.py) changes tray visibility and
icon style, checks the recent-copy text, and opens the popup with the icon hidden.
The [footer menu test](tests/footer_menu_smoke.py) clicks the menu rows with real
X11 pointer events, captures About and both clear confirmations, and checks the
quit shortcut.
The [fixed pins test](tests/sticky_pins_smoke.py) scrolls a long real popup with
pins at the top and bottom, checks their screen positions and height limit,
and moves selection across the two sections with arrow keys.
The [shortcut behavior test](tests/action_shortcuts_behavior.py) checks validation,
conflicts, disabled keys, and persistence.
The [search test](tests/search_behavior.py) verifies matching modes, fuzzy
ranking, and snippets that keep later matches visible.
The [install test](tests/install_smoke.py) checks a temporary user installation,
app-menu entry, launch, uninstall, and preservation of history.
