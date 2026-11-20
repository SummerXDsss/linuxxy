"""Frosted, rounded popup surface for composited X11 desktops."""

import math

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

CORNER_RADIUS = 20


def blur_pixbuf(pixbuf):
    width, height = pixbuf.get_width(), pixbuf.get_height()
    try:
        from PIL import Image, ImageFilter

        mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
        image = Image.frombytes(mode, (width, height), pixbuf.get_pixels(),
                                "raw", mode, pixbuf.get_rowstride(), 1)
        image = image.filter(ImageFilter.GaussianBlur(radius=18))
        channels = len(mode)
        return GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(image.tobytes()), GdkPixbuf.Colorspace.RGB,
            channels == 4, 8, width, height, width * channels)
    except ImportError:
        # Keep the glass option usable without Pillow, with a softer scaled blur.
        small = pixbuf.scale_simple(max(1, width // 12), max(1, height // 12),
                                    GdkPixbuf.InterpType.BILINEAR)
        return small.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)


def rounded_path(cr, width, height, radius):
    radius = min(radius, width / 2, height / 2)
    cr.new_sub_path()
    cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
    cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
    cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
    cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


class GlassWindow(Gtk.Window):
    """Paints a blurred snapshot below GTK controls when the glass theme is active."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.glass_enabled = False
        self.glass_dark = False
        self.backdrop = None
        self.backdrop_origin = (0, 0)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(False)

    def set_glass(self, enabled, dark=False):
        self.glass_enabled = enabled
        self.glass_dark = dark
        self.set_app_paintable(enabled)
        if not enabled:
            self.backdrop = None
        self.queue_draw()

    def capture_backdrop(self, x, y):
        self.backdrop = None
        if not self.glass_enabled:
            return
        root = Gdk.get_default_root_window()
        monitor = Gdk.Display.get_default().get_monitor_at_point(x, y)
        area = monitor.get_geometry()
        left = max(0, area.x)
        top = max(0, area.y)
        right = min(root.get_width(), area.x + area.width)
        bottom = min(root.get_height(), area.y + area.height)
        if right <= left or bottom <= top:
            return
        try:
            image = Gdk.pixbuf_get_from_window(root, left, top, right - left, bottom - top)
            if image is not None:
                self.backdrop = blur_pixbuf(image)
                self.backdrop_origin = (left, top)
        except (GLib.Error, ValueError):
            pass
        self.queue_draw()

    def do_draw(self, cr):
        if self.glass_enabled:
            cr.set_antialias(cairo.ANTIALIAS_BEST)
            width, height = self.get_allocated_width(), self.get_allocated_height()
            if width > 0 and height > 0:
                cr.save()
                rounded_path(cr, width, height, CORNER_RADIUS)
                cr.clip()
                if self.glass_dark:
                    cr.set_source_rgba(.09, .11, .15, .92)
                else:
                    cr.set_source_rgba(.86, .90, .96, .92)
                cr.paint()
                if self.backdrop is not None:
                    window = self.get_window()
                    _ok, x, y = window.get_origin()
                    Gdk.cairo_set_source_pixbuf(cr, self.backdrop,
                                                self.backdrop_origin[0] - x,
                                                self.backdrop_origin[1] - y)
                    cr.paint()
                tint = cairo.LinearGradient(0, 0, width * .35, height)
                if self.glass_dark:
                    tint.add_color_stop_rgba(0, .16, .19, .25, .56)
                    tint.add_color_stop_rgba(1, .09, .12, .17, .69)
                else:
                    tint.add_color_stop_rgba(0, 1, 1, 1, .48)
                    tint.add_color_stop_rgba(1, .91, .95, 1, .62)
                cr.set_source(tint)
                cr.paint()
                cr.restore()

                cr.save()
                rounded_path(cr, width, height, CORNER_RADIUS)
                highlight = cairo.LinearGradient(0, 0, width, height)
                if self.glass_dark:
                    highlight.add_color_stop_rgba(0, 1, 1, 1, .62)
                    highlight.add_color_stop_rgba(.5, 1, 1, 1, .16)
                    highlight.add_color_stop_rgba(1, 1, 1, 1, .32)
                else:
                    highlight.add_color_stop_rgba(0, 1, 1, 1, .95)
                    highlight.add_color_stop_rgba(.5, .70, .79, .91, .42)
                    highlight.add_color_stop_rgba(1, 1, 1, 1, .80)
                cr.set_source(highlight)
                cr.set_line_width(2)
                cr.stroke()
                cr.restore()
            cr.save()
            rounded_path(cr, width, height, CORNER_RADIUS)
            cr.clip()
            result = Gtk.Window.do_draw(self, cr)
            cr.restore()
            return result
        return Gtk.Window.do_draw(self, cr)
