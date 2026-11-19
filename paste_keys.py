"""Observe X11 paste keys without taking the shortcut away from other apps."""

import threading

from Xlib import X, XK, display
from Xlib.ext import record
from Xlib.protocol import rq
from gi.repository import GLib


class PasteKeys:
    def __init__(self, on_paste):
        self.on_paste = on_paste
        self.control = display.Display()
        if not self.control.has_extension("RECORD"):
            self.control.close()
            raise RuntimeError("X11 RECORD extension is unavailable")
        self.control.record_get_version(0, 0)
        self.keycode = self.control.keysym_to_keycode(XK.XK_v)
        self.down = False
        self.closed = False
        self.context = self.control.record_create_context(
            0, [record.AllClients], [{
                "core_requests": (0, 0), "core_replies": (0, 0),
                "ext_requests": (0, 0, 0, 0), "ext_replies": (0, 0, 0, 0),
                "delivered_events": (0, 0),
                "device_events": (X.KeyPress, X.KeyRelease),
                "errors": (0, 0), "client_started": False,
                "client_died": False,
            }]
        )
        self.control.sync()
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()

    def _watch(self):
        self.reader = display.Display()
        try:
            self.reader.record_enable_context(self.context, self._event)
        except Exception:
            if not self.closed:
                GLib.idle_add(self._failed)
        finally:
            self.reader.close()

    def _event(self, reply):
        if self.closed or reply.category != record.FromServer or reply.client_swapped:
            return
        data = reply.data
        while len(data) >= 32:
            event, data = rq.EventField(None).parse_binary_value(
                data, self.reader.display, None, None
            )
            if event.detail != self.keycode:
                continue
            if event.type == X.KeyPress:
                self.down = bool(event.state & X.ControlMask)
            elif event.type == X.KeyRelease and self.down:
                self.down = False
                GLib.idle_add(self.on_paste)

    def _failed(self):
        self.close()
        return False

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.control.record_disable_context(self.context)
        self.control.sync()
        self.thread.join(timeout=1)
        self.control.record_free_context(self.context)
        self.control.close()
