"""Serve multiple clipboard MIME targets to X11 applications."""

from Xlib import X, Xatom, display, protocol
from gi.repository import GLib


class X11Clipboard:
    def __init__(self):
        self.display = display.Display()
        root = self.display.screen().root
        self.window = root.create_window(-10, -10, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent)
        self.clipboard = self.display.intern_atom("CLIPBOARD")
        self.targets = self.display.intern_atom("TARGETS")
        self.formats = {}
        self.watch = GLib.io_add_watch(self.display.fileno(), GLib.IO_IN, self._events)

    def set(self, formats):
        self.formats = {
            self.display.intern_atom(name): value for name, value in formats.items()
            if value and len(value) <= 200_000
        }
        self.window.set_selection_owner(self.clipboard, X.CurrentTime)
        self.display.sync()
        if not self.is_owner():
            raise RuntimeError("Could not own the X11 clipboard")

    def is_owner(self):
        owner = self.display.get_selection_owner(self.clipboard)
        return getattr(owner, "id", owner) == self.window.id

    def _events(self, *_):
        while self.display.pending_events():
            event = self.display.next_event()
            if event.type == X.SelectionRequest:
                self._serve(event)
            elif event.type == X.SelectionClear:
                self.formats = {}
        return True

    def _serve(self, event):
        property_atom = event.property or event.target
        if event.target == self.targets:
            values = [self.targets, *self.formats.keys()]
            event.requestor.change_property(property_atom, Xatom.ATOM, 32, values)
        elif event.target in self.formats:
            value = self.formats[event.target]
            # XChangeProperty cannot transport arbitrarily large data without
            # implementing INCR. Keep rich formats below the safe request size.
            if len(value) <= 200_000:
                event.requestor.change_property(property_atom, event.target, 8, value)
            else:
                property_atom = X.NONE
        else:
            property_atom = X.NONE
        notify = protocol.event.SelectionNotify(
            time=event.time,
            requestor=event.requestor,
            selection=event.selection,
            target=event.target,
            property=property_atom,
        )
        event.requestor.send_event(notify)
        self.display.flush()

    def close(self):
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None
        self.window.destroy()
        self.display.close()
