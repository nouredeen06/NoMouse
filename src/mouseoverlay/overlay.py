"""GTK3 overlay window: row/column labeled grid, 3-stage zoom-to-click.

Alternate interaction model (branch: rowcol-grid). Each cell is labeled with
a row number (1-9) and a column letter (a-p), e.g. "1a" or "9i". Type the
pair in either order (both "1a" and "a1" work) - as soon as both halves are
typed it auto-confirms, no Enter needed:
  - plain             -> left-click that cell's center
  - held Shift         -> zoom into that cell instead (up to 3 stages)
  - held Ctrl          -> right-click that cell's center
Typing just a digit highlights that row; typing just a letter highlights
that column. Backspace on an empty entry goes back one zoom stage. Escape
cancels. Enter with an empty entry clicks the center of the current region
(Ctrl+Enter right-clicks it).

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


def _col_letter(idx: int) -> str:
    return chr(ord("a") + idx)


class _ParsedInput:
    """Result of parsing the entry text against the current stage's grid."""

    def __init__(self, row: Optional[int], col: Optional[int], valid: bool):
        self.row = row  # 1-indexed, or None
        self.col = col  # 0-indexed (a=0), or None
        self.valid = valid  # False if the text contains junk / out-of-range parts

    @property
    def is_pair(self) -> bool:
        return self.valid and self.row is not None and self.col is not None


def _parse_input(text: str, cols: int, rows: int) -> _ParsedInput:
    text = text.strip().lower()

    digits = "".join(c for c in text if c.isdigit())
    letters = "".join(c for c in text if c.isalpha())

    if len(digits) + len(letters) != len(text):
        return _ParsedInput(None, None, valid=False)

    row = None
    if digits:
        if len(digits) > 1 or not (1 <= int(digits) <= rows):
            return _ParsedInput(None, None, valid=False)
        row = int(digits)

    col = None
    if letters:
        if len(letters) > 1:
            return _ParsedInput(None, None, valid=False)
        idx = ord(letters) - ord("a")
        if not (0 <= idx < cols):
            return _ParsedInput(None, None, valid=False)
        col = idx

    return _ParsedInput(row, col, valid=True)


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
        self.partial: _ParsedInput = _ParsedInput(None, None, True)
        self._last_key_state = Gdk.ModifierType(0)

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
        self.entry.set_placeholder_text("1a/a1 = click, +Shift = zoom, +Ctrl = right")
        self.entry.get_style_context().add_class("mouseoverlay-entry")
        self.entry.connect("changed", self._on_entry_changed)
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

    def _stage_dims(self) -> tuple[int, int]:
        return STAGE_DIMS[self.stage_index]

    def _on_draw(self, _widget, cr) -> bool:
        region = self.current_region
        cols, rows = self._stage_dims()
        ox, oy = self.monitor.x, self.monitor.y
        cw = region.w / cols
        ch = region.h / rows

        # highlight: a specific cell if a full pair is typed, else a whole
        # row or column band if only one half of the pair is typed so far.
        if self.partial.is_pair:
            rect = cell_rect_rc(region, cols, rows, self.partial.row, self.partial.col)
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.45)
            cr.rectangle(rect.x - ox, rect.y - oy, rect.w, rect.h)
            cr.fill()
        elif self.partial.row is not None:
            y = region.y - oy + (self.partial.row - 1) * ch
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.25)
            cr.rectangle(region.x - ox, y, region.w, ch)
            cr.fill()
        elif self.partial.col is not None:
            x = region.x - ox + self.partial.col * cw
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

    def _on_entry_changed(self, _entry) -> None:
        cols, rows = self._stage_dims()
        self.partial = _parse_input(self.entry.get_text(), cols, rows)
        self.drawing_area.queue_draw()

        if self.partial.is_pair:
            self._confirm_pair(self.partial.row, self.partial.col, self._last_key_state)

    def _on_entry_key_press(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        if event.keyval == Gdk.KEY_BackSpace and self.entry.get_text() == "":
            self._go_back()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.entry.get_text() == "":
                right = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
                self._do_click(self.current_region, "right" if right else "left")
            return True
        # Stash modifier state so the "changed" handler (fired by the default
        # text-insert handling that runs after we return False here) knows
        # whether Shift/Ctrl were held for the keystroke that completes a pair.
        self._last_key_state = event.state
        return False

    def _on_key_press(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _go_back(self) -> None:
        if not self.history:
            return
        self.current_region, self.stage_index = self.history.pop()
        self.entry.set_text("")
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
            self.partial = _ParsedInput(None, None, True)
            self.entry.set_text("")
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
