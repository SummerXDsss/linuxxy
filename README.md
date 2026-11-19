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

1. Copy some text in any application.
2. Press **Super+Shift+V** or click the tray icon.
3. Type to search. Press **Down** to focus results, then use arrow keys.
4. Press **Enter** or double-click a result to paste it into the previous window.
5. Press **Ctrl+Enter** or click **Copy** to place it on the clipboard without
   pasting. **Escape** hides the window.

You can also pin or delete the selected entry, or clear all unpinned entries.
Open **Preferences…** from the tray menu or press **Ctrl+,** while the popup is
open. You can change the opening shortcut, default paste action, history limit,
clipboard check interval, search mode (exact, fuzzy, regex, or mixed), pinned
item position, popup position, clear-on-quit behavior, and launch at
login. Preferences are saved in `$XDG_CONFIG_HOME/linuxxy/settings.json`.
Enabling launch at login creates `$XDG_CONFIG_HOME/autostart/linuxxy.desktop`.

History is stored as plain text in an unencrypted SQLite database at
`$XDG_DATA_HOME/linuxxy/history.sqlite`, usually
`~/.local/share/linuxxy/history.sqlite`. The current version handles text only.
Global shortcuts and automatic paste require X11. Wayland support, images,
files, and rich text are future work.

## License

Linuxxy is MIT licensed; see [LICENSE](LICENSE). Maccy's original MIT license
and copyright notice are preserved in [LICENSE-Maccy](LICENSE-Maccy).
