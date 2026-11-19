"""Small real GTK target window for the X11 interaction test."""
import os
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, GdkX11, GLib

window = Gtk.Window(title='Linuxxy paste target')
window.set_default_size(440, 100)
entry = Gtk.Entry()
entry.set_text('hello linuxxy clipboard')
entry.select_region(0, -1)
window.add(entry)
entry.connect('changed', lambda widget: Path(os.environ['LINUXXY_TEST_VALUE']).write_text(widget.get_text()))
window.connect('destroy', Gtk.main_quit)
window.show_all()
entry.grab_focus()
Path(os.environ['LINUXXY_TEST_VALUE']).write_text(entry.get_text())
Path(os.environ['LINUXXY_TEST_XID']).write_text(str(GdkX11.X11Window.get_xid(window.get_window())))
def commands():
    command = Path(os.environ['LINUXXY_TEST_COMMAND'])
    if command.exists():
        if command.read_text() == 'clear':
            entry.set_text('')
        command.unlink()
    return True
GLib.timeout_add(50, commands)
Gtk.main()
