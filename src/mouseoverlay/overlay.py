"""GTK3 overlay window: numbered grid + input bar, multi-stage zoom-to-click."""

import logging
import re
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from mouseoverlay.config import Config, StageGrid
from mouseoverlay.grid import Rect, cell_rect as _cell_rect
from mouseoverlay.monitors import MonitorGeometry

log = logging.getLogger(__name__)

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    _HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    GtkLayerShell = None
    _HAS_LAYER_SHELL = False

_NUMBER_RE = re.compile(r"^(\d+)$")
_NUMBER_RIGHT_RE = re.compile(r"^(\d+)r$")
_RIGHT_RE = re.compile(r"^r$")


class OverlayWindow(Gtk.Window):
    def __init__(
        self,
        monitor: MonitorGeometry,
        config: Config,
        backend_name: str,
        click_fn: Callable[[str, int, int, str], None],
    ):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.monitor = monitor
        self.config = config
        self.backend_name = backend_name
        self.click_fn = click_fn

        self.stages = [config.stage1, config.stage2, config.stage3]
        self.stage_index = 0
        self.current_region = Rect(monitor.x, monitor.y, monitor.width, monitor.height)
        self.history: list[tuple[Rect, int]] = []

        self._setup_window()
        self._build_ui()

    # -- window setup -----------------------------------------------------

    def _setup_window(self) -> None:
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)

        css = Gtk.CssProvider()
        css.load_from_data(
            f"""
            window {{ background-color: {self.config.background_rgba}; }}
            .mouseoverlay-inputbar {{
                background-color: rgba(20, 20, 20, 0.92);
                border: 2px solid rgba(255, 255, 255, 0.6);
                border-radius: 10px;
                padding: 8px 16px;
            }}
            .mouseoverlay-entry, .mouseoverlay-entry:focus {{
                background-color: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                color: #ffffff;
                font-size: 22px;
            }}
            """.encode()
        )
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        if self.backend_name == "hyprland" and _HAS_LAYER_SHELL:
            self._setup_layer_shell()
        else:
            self._setup_x11_window()

        self.connect("key-press-event", self._on_key_press)

    def _setup_layer_shell(self) -> None:
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (
            GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
            GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT,
        ):
            GtkLayerShell.set_anchor(self, edge, True)

        gdk_monitor = self._find_gdk_monitor()
        if gdk_monitor is not None:
            GtkLayerShell.set_monitor(self, gdk_monitor)

    def _find_gdk_monitor(self):
        display = self.get_display()
        for i in range(display.get_n_monitors()):
            m = display.get_monitor(i)
            geo = m.get_geometry()
            if geo.x == self.monitor.x and geo.y == self.monitor.y:
                return m
        return None

    def _setup_x11_window(self) -> None:
        self.set_keep_above(True)
        self.set_accept_focus(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.move(self.monitor.x, self.monitor.y)
        self.resize(self.monitor.width, self.monitor.height)

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        overlay = Gtk.Overlay()
        self.add(overlay)

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self._on_draw)
        overlay.add(self.drawing_area)

        self.entry = Gtk.Entry()
        self.entry.set_alignment(0.5)
        self.entry.set_width_chars(12)
        self.entry.set_placeholder_text("type cell number, Enter to click...")
        self.entry.get_style_context().add_class("mouseoverlay-entry")
        self.entry.connect("activate", self._on_activate)
        self.entry.connect("key-press-event", self._on_entry_key_press)

        bar = Gtk.Box()
        bar.set_valign(Gtk.Align.END)
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_margin_bottom(32)
        bar.get_style_context().add_class("mouseoverlay-inputbar")
        bar.pack_start(self.entry, False, False, 0)
        overlay.add_overlay(bar)
        overlay.set_overlay_pass_through(bar, False)

    def show_all_and_focus(self) -> None:
        self.show_all()
        self.entry.grab_focus()

    # -- drawing --------------------------------------------------------

    def _on_draw(self, _widget, cr) -> bool:
        region = self.current_region
        grid = self.stages[self.stage_index]

        # local coords: drawing area covers the whole window, window is placed
        # at monitor.x/monitor.y, so subtract monitor origin to get local coords.
        ox, oy = self.monitor.x, self.monitor.y

        cr.set_line_width(1.5)
        cr.set_source_rgba(1, 1, 1, 0.85)

        cw = region.w / grid.cols
        ch = region.h / grid.rows

        for col in range(grid.cols + 1):
            x = region.x - ox + col * cw
            cr.move_to(x, region.y - oy)
            cr.line_to(x, region.y - oy + region.h)
        for row in range(grid.rows + 1):
            y = region.y - oy + row * ch
            cr.move_to(region.x - ox, y)
            cr.line_to(region.x - ox + region.w, y)
        cr.stroke()

        font_size = max(10, min(cw, ch) / 4)
        cr.select_font_face("sans-serif")
        cr.set_font_size(font_size)
        for n in range(1, grid.cols * grid.rows + 1):
            rect = _cell_rect(region, grid, n)
            label = str(n)
            extents = cr.text_extents(label)
            tx = rect.x - ox + rect.w / 2 - extents.width / 2 - extents.x_bearing
            ty = rect.y - oy + rect.h / 2 - extents.height / 2 - extents.y_bearing
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.move_to(tx, ty)
            cr.show_text(label)

        return False

    # -- input handling ---------------------------------------------------

    def _on_entry_key_press(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        if event.keyval == Gdk.KEY_BackSpace and self.entry.get_text() == "":
            self._go_back()
            return True
        return False

    def _go_back(self) -> None:
        if not self.history:
            return
        self.current_region, self.stage_index = self.history.pop()
        self.entry.set_text("")
        self.drawing_area.queue_draw()

    def _on_key_press(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _on_activate(self, _entry) -> None:
        text = self.entry.get_text().strip()

        if text == "":
            self._do_click(self.current_region, "left")
            return

        if _RIGHT_RE.match(text):
            self._do_click(self.current_region, "right")
            return

        m = _NUMBER_RIGHT_RE.match(text)
        if m:
            n = int(m.group(1))
            grid = self.stages[self.stage_index]
            if 1 <= n <= grid.cols * grid.rows:
                rect = _cell_rect(self.current_region, grid, n)
                self._do_click(rect, "right")
            else:
                self._reject()
            return

        m = _NUMBER_RE.match(text)
        if m:
            n = int(m.group(1))
            grid = self.stages[self.stage_index]
            if not (1 <= n <= grid.cols * grid.rows):
                self._reject()
                return
            rect = _cell_rect(self.current_region, grid, n)
            if self.stage_index < len(self.stages) - 1:
                self.history.append((self.current_region, self.stage_index))
                self.current_region = rect
                self.stage_index += 1
                self.entry.set_text("")
                self.drawing_area.queue_draw()
            else:
                self._do_click(rect, "left")
            return

        self._reject()

    def _reject(self) -> None:
        self.entry.set_text("")

    def _do_click(self, rect: Rect, button: str) -> None:
        # Destroy the overlay before clicking, not after: it's a topmost
        # full-screen surface, so a click fired while it's still up lands on
        # the overlay itself instead of passing through to the window
        # underneath. Give the compositor one idle cycle to actually unmap it
        # before firing the synthetic click.
        cx, cy = rect.center()
        backend_name = self.backend_name
        click_fn = self.click_fn
        self.destroy()
        GLib.timeout_add(50, lambda: (click_fn(backend_name, cx, cy, button), False)[1])
