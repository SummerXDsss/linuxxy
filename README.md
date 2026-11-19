# Linuxxy

A lightweight, keyboard-first clipboard manager for Linux X11 desktops, inspired
by [Maccy](https://github.com/p0deje/Maccy).

## Requirements

- Linux desktop using X11 and a system tray
- Python 3
- GTK 3 and PyGObject (`python3-gi` on Debian/Ubuntu)
- python-xlib (`python3-xlib` on Debian/Ubuntu)
- XTEST X11 extension (normally installed with Xorg)

On Debian/Ubuntu, install the Python dependencies with:

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 python3-xlib
```

## Run

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

Use **Ctrl+1…9** to copy a visible result or **Alt+1…9** to paste it.
Click a row to choose it,
or right-click for Paste, Copy, Preview, Pin, and Delete. You can also use
**Alt+P** to pin and **Alt+Delete** to delete the selected entry.
Use **Ctrl+Alt+Delete** to clear unpinned history or **Ctrl+Alt+Shift+Delete**
to clear all history, including pinned entries. Clear unpinned history from the footer.
Press **Space** on a selected result to preview its full text or image.
Open **Preferences…** from the footer or tray menu, or press **Ctrl+,** while
the popup is open. General, Storage, and Appearance pages cover the opening
shortcut, default paste action, text/image/file capture, history limit, clipboard
check interval, search mode (exact, fuzzy, regex, or mixed), pinned item
position, popup position, footer visibility, clear-on-quit behavior, and launch
at login. Preferences are saved in `$XDG_CONFIG_HOME/linuxxy/settings.json`.
Enabling launch at login creates `$XDG_CONFIG_HOME/autostart/linuxxy.desktop`.

History is stored in an unencrypted SQLite database at
`$XDG_DATA_HOME/linuxxy/history.sqlite`, usually
`~/.local/share/linuxxy/history.sqlite`. The current version handles plain
text, HTML alongside text, images, and file URI lists. Global shortcuts,
automatic paste, and restoring rich formats require X11. Wayland support is
future work. Rich clipboard payloads over 200 KB fall back to plain text when
restored, and file/rich clipboard contents are owned by Linuxxy while it runs.

## License

Linuxxy is MIT licensed; see [LICENSE](LICENSE). Maccy's original MIT license
and copyright notice are preserved in [LICENSE-Maccy](LICENSE-Maccy).

## Desktop test

The [UI smoke test](tests/ui_smoke.py) starts Linuxxy and a separate GTK paste
target, sends real X11 keyboard shortcuts, and saves screenshots of the popup,
preview, preferences, and pasted result to [screenshots](screenshots). The
[visual sample](tests/visual_sample.py) renders the popup and all three settings
pages with known sample data. These scripts need `wmctrl`, `xwd`, and `ffmpeg`
in addition to the runtime dependencies. Run the smoke test from an X11
desktop when no other application has an active keyboard grab.
The [format smoke test](tests/formats_smoke.py) verifies HTML and file copying
between separate X11 applications and restores the clipboard afterward.
