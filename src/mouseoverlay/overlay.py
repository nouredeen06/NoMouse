"""GTK3 overlay window: row/column labeled grid, 3-stage zoom-to-click.

Alternate interaction model (branch: rowcol-grid). Each cell is labeled with
a row number (1-9) and a column letter (a-p), e.g. "1a" or "9i". Press the
digit and letter keys in either order - as soon as both are set it
auto-confirms, no Enter needed:
  - plain               -> left-click that cell's center
  - held Shift on the
    completing keystroke -> zoom into that cell instead (up to 3 stages)
  - held Ctrl on the
    completing keystroke -> right-click that cell's center
Only one digit and one letter can be held at a time (further presses of an
already-filled slot are ignored). Backspace clears the most recently set
slot, or goes back one zoom stage if both are empty. Escape cancels. Enter
with nothing typed clicks the center of the current region (Ctrl+Enter
right-clicks it).

Key reading is done from the physical (unshifted) keyval rather than the
text GTK would insert, so Shift+1 is read as digit 1 (not '!').

No persistent input box: a one-line hint fades out on its own (or on the
first keystroke) and grid highlighting alone shows progress after that.
Set show_hint = false in config.toml to skip the hint entirely.

Stage grid sizes are fixed (not user-configurable), per design decision.
"""

import logging
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from mouseoverlay.config import Config
from mouseoverlay.grid import Rect, cell_rect_rc
from mouseoverlay.monitors import MonitorGeometry

log = logging.getLogger(__name__)

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    _HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    GtkLayerShell = None
    _HAS_LAYER_SHELL = False

# (cols, rows) per stage. Stage 1 matches the spec exactly (16x9 = ~120x120px
# cells on a 1920x1080 screen). Stages 2/3 must stay small: they subdivide an
# already-small stage-1 cell, so a dense grid there produces unreadable
# labels. 4x3 keeps stage-2 cells around 30x40px (readable); a stage-2 click
# is already far more precise than the old single-stage grid, so stage 3
# only needs a light 2x2 split for the rare case that needs it.
STAGE_DIMS = [(16, 9), (4, 3), (2, 2)]

HINT_DURATION_MS = 2500


def _col_letter(idx: int) -> str:
    return chr(ord("a") + idx)


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

        self.stage_index = 0
        self.current_region = Rect(monitor.x, monitor.y, monitor.width, monitor.height)
        self.history: list[tuple[Rect, int]] = []
        self.typed_row: Optional[int] = None  # 1-indexed
        self.typed_col: Optional[int] = None  # 0-indexed (a=0)

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
                min-width: 220px;
            }}
            .mouseoverlay-label {{
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

        self.hint_bar: Optional[Gtk.Box] = None
        if self.config.show_hint:
            label = Gtk.Label(label="1a/a1=click  +Shift=zoom  +Ctrl=right")
            label.get_style_context().add_class("mouseoverlay-label")

            bar = Gtk.Box()
            bar.set_valign(Gtk.Align.END)
            bar.set_halign(Gtk.Align.CENTER)
            bar.set_margin_bottom(32)
            bar.get_style_context().add_class("mouseoverlay-inputbar")
            bar.pack_start(label, True, True, 0)
            overlay.add_overlay(bar)
            overlay.set_overlay_pass_through(bar, True)

            self.hint_bar = bar
            GLib.timeout_add(HINT_DURATION_MS, self._hide_hint)

    def show_all_and_focus(self) -> None:
        self.show_all()
        self.grab_focus()

    # -- drawing --------------------------------------------------------

    def _stage_dims(self) -> tuple[int, int]:
        return STAGE_DIMS[self.stage_index]

    def _hide_hint(self) -> bool:
        if self.hint_bar is not None:
            self.hint_bar.hide()
        return False  # one-shot timeout, don't repeat

    def _on_draw(self, _widget, cr) -> bool:
        region = self.current_region
        cols, rows = self._stage_dims()
        ox, oy = self.monitor.x, self.monitor.y
        cw = region.w / cols
        ch = region.h / rows

        # highlight: a specific cell if both are set, else a whole row or
        # column band if only one half is set so far.
        if self.typed_row is not None and self.typed_col is not None:
            rect = cell_rect_rc(region, cols, rows, self.typed_row, self.typed_col)
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.45)
            cr.rectangle(rect.x - ox, rect.y - oy, rect.w, rect.h)
            cr.fill()
        elif self.typed_row is not None:
            y = region.y - oy + (self.typed_row - 1) * ch
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.25)
            cr.rectangle(region.x - ox, y, region.w, ch)
            cr.fill()
        elif self.typed_col is not None:
            x = region.x - ox + self.typed_col * cw
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.25)
            cr.rectangle(x, region.y - oy, cw, region.h)
            cr.fill()

        cr.set_line_width(1.5)
        cr.set_source_rgba(1, 1, 1, 0.85)
        for col in range(cols + 1):
            x = region.x - ox + col * cw
            cr.move_to(x, region.y - oy)
            cr.line_to(x, region.y - oy + region.h)
        for row in range(rows + 1):
            y = region.y - oy + row * ch
            cr.move_to(region.x - ox, y)
            cr.line_to(region.x - ox + region.w, y)
        cr.stroke()

        font_size = max(9, min(cw, ch) / 3.2)
        cr.select_font_face("sans-serif")
        cr.set_font_size(font_size)
        for row in range(1, rows + 1):
            for col in range(cols):
                label = f"{row}{_col_letter(col)}"
                cell = cell_rect_rc(region, cols, rows, row, col)
                extents = cr.text_extents(label)
                tx = cell.x - ox + cell.w / 2 - extents.width / 2 - extents.x_bearing
                ty = cell.y - oy + cell.h / 2 - extents.height / 2 - extents.y_bearing
                cr.set_source_rgba(1, 1, 1, 0.95)
                cr.move_to(tx, ty)
                cr.show_text(label)

        return False

    # -- input handling ---------------------------------------------------

    def _base_keyval(self, event) -> int:
        """Keyval for this key ignoring modifiers, so Shift+1 reads as '1'
        rather than the shifted symbol ('!' on a US layout)."""
        keymap = Gdk.Keymap.get_for_display(self.get_display())
        ok, keyval, _group, _level, _consumed = keymap.translate_keyboard_state(
            event.hardware_keycode, Gdk.ModifierType(0), event.group
        )
        return keyval if ok else event.keyval

    def _on_key_press(self, _widget, event) -> bool:
        self._hide_hint()

        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True

        if event.keyval == Gdk.KEY_BackSpace:
            self._backspace()
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.typed_row is None and self.typed_col is None:
                right = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
                self._do_click(self.current_region, "right" if right else "left")
            return True

        base = self._base_keyval(event)
        cols, rows = self._stage_dims()

        digit = None
        if Gdk.KEY_0 <= base <= Gdk.KEY_9:
            digit = base - Gdk.KEY_0
        elif Gdk.KEY_KP_0 <= base <= Gdk.KEY_KP_9:
            digit = base - Gdk.KEY_KP_0

        if digit is not None:
            if self.typed_row is None and 1 <= digit <= rows:
                self.typed_row = digit
                self._after_keystroke(event.state)
            return True

        if Gdk.KEY_a <= base <= Gdk.KEY_z:
            idx = base - Gdk.KEY_a
            if self.typed_col is None and idx < cols:
                self.typed_col = idx
                self._after_keystroke(event.state)
            return True

        return True  # swallow everything else while the overlay is up

    def _after_keystroke(self, mod_state: Gdk.ModifierType) -> None:
        self.drawing_area.queue_draw()
        if self.typed_row is not None and self.typed_col is not None:
            self._confirm_pair(self.typed_row, self.typed_col, mod_state)

    def _backspace(self) -> None:
        if self.typed_col is not None:
            self.typed_col = None
        elif self.typed_row is not None:
            self.typed_row = None
        else:
            self._go_back()
            return
        self.drawing_area.queue_draw()

    def _go_back(self) -> None:
        if not self.history:
            return
        self.current_region, self.stage_index = self.history.pop()
        self.drawing_area.queue_draw()

    def _confirm_pair(self, row: int, col: int, mod_state: Gdk.ModifierType) -> None:
        cols, rows = self._stage_dims()
        rect = cell_rect_rc(self.current_region, cols, rows, row, col)

        ctrl = bool(mod_state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(mod_state & Gdk.ModifierType.SHIFT_MASK)

        if ctrl:
            self._do_click(rect, "right")
            return

        if shift and self.stage_index < len(STAGE_DIMS) - 1:
            self.history.append((self.current_region, self.stage_index))
            self.current_region = rect
            self.stage_index += 1
            self.typed_row = None
            self.typed_col = None
            self.drawing_area.queue_draw()
            return

        self._do_click(rect, "left")

    def _do_click(self, rect: Rect, button: str) -> None:
        # Destroy the overlay before clicking: it's a topmost full-screen
        # surface, so a click fired while it's still up lands on the overlay
        # itself instead of passing through to the window underneath. Give
        # the compositor one idle cycle to actually unmap it first.
        cx, cy = rect.center()
        backend_name = self.backend_name
        click_fn = self.click_fn
        self.destroy()
        GLib.timeout_add(50, lambda: (click_fn(backend_name, cx, cy, button), False)[1])
