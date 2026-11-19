"""X11 global shortcut, active-window restoration, and synthetic paste."""

from Xlib import X, XK, Xatom, display, protocol
from Xlib.ext import xtest
from gi.repository import GLib


def parse_shortcut(shortcut):
    if not isinstance(shortcut, str):
        raise ValueError("Shortcut must be text")
    parts = [part.strip().lower() for part in shortcut.split("+")]
    mapping = {"super": X.Mod4Mask, "shift": X.ShiftMask,
               "ctrl": X.ControlMask, "alt": X.Mod1Mask}
    if len(parts) < 2 or len(set(parts)) != len(parts):
        raise ValueError("Use a shortcut such as Super+Shift+V")
    *modifiers, key = parts
    if any(part not in mapping for part in modifiers) or not any(
        part in ("super", "ctrl", "alt") for part in modifiers
    ):
        raise ValueError("Shortcut needs Super, Ctrl, or Alt and one key")
    if len(key) != 1 or not key.isascii() or not key.isalnum():
        raise ValueError("Shortcut key must be one letter or digit")
    return key, sum(mapping[part] for part in modifiers)


class X11:
    def __init__(self, on_shortcut, shortcut="Super+Shift+V"):
        key, self.modifiers = parse_shortcut(shortcut)
        self.display = display.Display()
        self.root = self.display.screen().root
        self.on_shortcut = on_shortcut
        self.keycode = self.display.keysym_to_keycode(XK.string_to_keysym(key))
        if self.keycode == 0:
            self.display.close()
            raise ValueError(f"Shortcut key {key} is unavailable")
        self.masks = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
        self.grabbed = []
        try:
            for mask in self.masks:
                errors = []
                self.root.grab_key(self.keycode, self.modifiers | mask, False,
                                   X.GrabModeAsync, X.GrabModeAsync,
                                   onerror=lambda error, _request: errors.append(error))
                self.display.sync()
                if errors:
                    raise RuntimeError(f"{shortcut} is already in use")
                self.grabbed.append(mask)
        except Exception:
            self.close()
            raise
        self.watch = GLib.io_add_watch(self.display.fileno(), GLib.IO_IN, self._events)

    def _events(self, *_):
        while self.display.pending_events():
            event = self.display.next_event()
            if event.type == X.KeyPress and event.detail == self.keycode:
                self.on_shortcut()
        return True

    def active_window(self):
        atom = self.display.intern_atom("_NET_ACTIVE_WINDOW")
        prop = self.root.get_full_property(atom, Xatom.WINDOW)
        return int(prop.value[0]) if prop and len(prop.value) else None

    def activate(self, window_id):
        if window_id is None:
            return
        window = self.display.create_resource_object("window", window_id)
        event = protocol.event.ClientMessage(
            window=window,
            client_type=self.display.intern_atom("_NET_ACTIVE_WINDOW"),
            data=(32, [2, X.CurrentTime, 0, 0, 0]),
        )
        self.root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.display.flush()

    def paste(self):
        ctrl = self.display.keysym_to_keycode(XK.XK_Control_L)
        v = self.display.keysym_to_keycode(XK.XK_v)
        for key, pressed in ((ctrl, True), (v, True), (v, False), (ctrl, False)):
            xtest.fake_input(self.display, X.KeyPress if pressed else X.KeyRelease, key)
        self.display.flush()

    def close(self):
        if getattr(self, "watch", None):
            GLib.source_remove(self.watch)
            self.watch = None
        for mask in self.grabbed:
            self.root.ungrab_key(self.keycode, self.modifiers | mask)
        self.display.flush()
        self.display.close()
