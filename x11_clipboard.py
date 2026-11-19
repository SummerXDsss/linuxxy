"""Serve multiple clipboard MIME targets to X11 applications."""

import time

from Xlib import X, Xatom, display, protocol
from gi.repository import GLib


class X11Clipboard:
    def __init__(self):
        self.display = display.Display()
        root = self.display.screen().root
        self.window = root.create_window(-10, -10, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent)
        self.clipboard = self.display.intern_atom("CLIPBOARD")
        self.targets = self.display.intern_atom("TARGETS")
        self.multiple = self.display.intern_atom("MULTIPLE")
        self.atom_pair = self.display.intern_atom("ATOM_PAIR")
        self.incr = self.display.intern_atom("INCR")
        self.clipboard_manager = self.display.intern_atom("CLIPBOARD_MANAGER")
        self.save_targets = self.display.intern_atom("SAVE_TARGETS")
        self.save_property = self.display.intern_atom("LINUXXY_SAVE_TARGETS")
        self.formats = {}
        self.transfers = {}
        self.save_result = None
        self.chunk_size = 64 * 1024
        self.watch = GLib.io_add_watch(self.display.fileno(), GLib.IO_IN, self._events)

    def set(self, formats):
        self.formats = {
            self.display.intern_atom(name): value for name, value in formats.items()
            if value
        }
        self.window.set_selection_owner(self.clipboard, X.CurrentTime)
        self.display.sync()
        if not self.is_owner():
            raise RuntimeError("Could not own the X11 clipboard")

    def is_owner(self):
        owner = self.display.get_selection_owner(self.clipboard)
        return getattr(owner, "id", owner) == self.window.id

    def store(self, timeout=3):
        if not self.is_owner() or not self.display.get_selection_owner(self.clipboard_manager):
            return False
        self.save_result = None
        self.window.change_property(self.save_property, Xatom.ATOM, 32,
                                    list(self.formats))
        self.window.convert_selection(self.clipboard_manager, self.save_targets,
                                      self.save_property, X.CurrentTime)
        self.display.flush()
        deadline = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while self.save_result is None and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(.01)
        return self.save_result is True

    def _events(self, *_):
        while self.display.pending_events():
            event = self.display.next_event()
            if event.type == X.SelectionRequest:
                self._serve(event)
            elif event.type == X.SelectionClear:
                self.formats = {}
            elif event.type == X.PropertyNotify and event.state == X.PropertyDelete:
                self._continue_transfer(event)
            elif event.type == X.SelectionNotify and event.selection == self.clipboard_manager:
                self.save_result = event.property != X.NONE
        return True

    def _serve(self, event):
        property_atom = event.property or event.target
        if event.target == self.multiple and event.property:
            pairs = event.requestor.get_full_property(property_atom, self.atom_pair)
            if pairs and len(pairs.value) % 2 == 0:
                values = list(pairs.value)
                for index in range(0, len(values), 2):
                    if not self._serve_one(event.requestor, values[index], values[index + 1]):
                        values[index + 1] = X.NONE
                event.requestor.change_property(property_atom, self.atom_pair, 32, values)
            else:
                property_atom = X.NONE
        elif not self._serve_one(event.requestor, event.target, property_atom):
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

    def _serve_one(self, requestor, target, property_atom):
        if property_atom == X.NONE:
            return False
        if target == self.targets:
            requestor.change_property(property_atom, Xatom.ATOM, 32,
                                      [self.targets, self.multiple, *self.formats.keys()])
            return True
        if target not in self.formats:
            return False
        value = self.formats[target]
        if len(value) <= self.chunk_size:
            requestor.change_property(property_atom, target, 8, value)
        else:
            requestor.change_attributes(event_mask=X.PropertyChangeMask)
            requestor.change_property(property_atom, self.incr, 32, [len(value)])
            self.transfers[(requestor.id, property_atom)] = (requestor, target, value, 0)
        return True

    def _continue_transfer(self, event):
        key = (event.window.id, event.atom)
        transfer = self.transfers.get(key)
        if not transfer:
            return
        requestor, target, value, offset = transfer
        chunk = value[offset:offset + self.chunk_size]
        requestor.change_property(event.atom, target, 8, chunk)
        if chunk:
            self.transfers[key] = (requestor, target, value, offset + len(chunk))
        else:
            del self.transfers[key]
            if not any(window_id == event.window.id for window_id, _ in self.transfers):
                requestor.change_attributes(event_mask=0)
        self.display.flush()

    def close(self):
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None
        self.transfers.clear()
        self.window.destroy()
        self.display.close()
