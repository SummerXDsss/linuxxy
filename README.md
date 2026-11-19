# Linuxxy

A lightweight, keyboard-first clipboard manager for Linux X11 desktops, inspired
by [Maccy](https://github.com/p0deje/Maccy).

## Requirements

- Linux desktop using X11 and a system tray
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

The process stays in the tray. A second instance exits rather than opening a
second clipboard watcher. Use the tray menu to pause monitoring or quit.

## Use

1. Copy text, an image, or files in any application.
2. Press **Super+Shift+V** or click the tray icon.
3. Type to search. Press **Down** to focus results, then use arrow keys.
4. Press **Enter** or click a result to copy it. Press **Alt+Enter** or
   **Alt+click** to paste it into the previous window. **Escape** hides the window.
   Use **Alt+Shift+Enter** or **Alt+Shift+click** to reverse the saved formatting
   preference for that paste (plain text by default).

Use **Ctrl+1…9** to copy a visible result or **Alt+1…9** to paste it.
Pinned entries get persistent letter shortcuts: **Ctrl+letter** copies,
**Alt+letter** pastes, and **Alt+Shift+letter** pastes plain text.
Click a row to choose it,
or right-click for Paste, Copy, Preview, Pin, and Delete. You can also use
**Alt+P** to pin and **Alt+Delete** to delete the selected entry.
Pinned entries can be moved with **Alt+Up/Down** or the right-click menu;
their letter shortcuts stay with each entry.
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
to clear all history, including pinned entries. Clear unpinned history from the footer.
Press **Space** on a selected result to preview its full text or image. A small
preview also appears after the selected item rests for 1.5 seconds by default.
Open **Preferences…** from the footer or tray menu, or press **Ctrl+,** while
the popup is open. General, Storage, and Appearance pages cover the opening
shortcut, default paste and formatting behavior, text/image/file capture, history
limit, clipboard check interval, history sorting (last copied, first copied, or most copied),
search mode (exact, fuzzy, regex, or mixed), match highlighting (bold, italic,
underline, or color), pinned item position, popup position, automatic preview
and its delay, image thumbnail height, hex color swatches, visible whitespace
symbols, search field visibility (always, while typing, or hidden), footer
visibility, clear-on-quit behavior, and launch at login. When the search field
is hidden, typing still filters the history; Backspace removes the last character.
Preferences are saved in
`$XDG_CONFIG_HOME/linuxxy/settings.json`.
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
The [search test](tests/search_behavior.py) verifies matching modes, fuzzy
ranking, and snippets that keep later matches visible.
The [install test](tests/install_smoke.py) checks a temporary user installation,
app-menu entry, launch, uninstall, and preservation of history.
