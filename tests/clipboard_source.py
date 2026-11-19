"""Keep a GTK clipboard owner responsive while X11 tests copy text."""

import os
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk


command = Path(os.environ['LINUXXY_TEST_CLIPBOARD_COMMAND'])
ack = Path(os.environ['LINUXXY_TEST_CLIPBOARD_ACK'])
clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


def copy_requested():
    if command.exists():
        value = command.read_text()
        command.unlink()
        clipboard.set_text(value, -1)
        ack.write_text(value)
    return True


GLib.timeout_add(25, copy_requested)
Gtk.main()
