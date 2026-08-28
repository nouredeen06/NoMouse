"""Locate the geometry of the currently focused monitor."""

import json
import logging
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class MonitorGeometry:
    x: int
    y: int
    width: int
    height: int
    scale: float = 1.0


def get_focused_monitor(backend: str) -> MonitorGeometry:
    if backend == "hyprland":
        return _get_focused_monitor_hyprland()
    return _get_focused_monitor_x11()


def _get_focused_monitor_hyprland() -> MonitorGeometry:
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "monitors"],
            capture_output=True, check=True, text=True,
        ).stdout
        monitors = json.loads(out)
        focused = next((m for m in monitors if m.get("focused")), None)
        if focused is None:
            log.warning("hyprctl monitors: no focused monitor found, using first")
            focused = monitors[0]
        return _geometry_from_hypr_monitor(focused)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, IndexError, KeyError) as exc:
        log.error("failed to query hyprctl monitors: %s", exc)
        raise


def _geometry_from_hypr_monitor(mon: dict) -> MonitorGeometry:
    """Build geometry in *logical* pixels.

    hyprctl reports ``width``/``height`` in physical device pixels but
    ``x``/``y`` (and the cursor coordinate space that ydotool / hyprctl
    cursorpos operate in) in logical pixels. On a fractionally scaled
    output the two disagree, so mixing a logical origin with a physical
    size makes the grid span past the real monitor and the pointer
    overshoot by the scale factor. Divide the size down to logical units
    so every coordinate the app produces is in the same space Hyprland
    moves the cursor in.
    """
    scale = mon.get("scale", 1.0) or 1.0
    transform = mon.get("transform", 0)
    phys_w, phys_h = mon["width"], mon["height"]
    if transform in (1, 3, 5, 7):  # 90/270-degree rotations swap axes
        phys_w, phys_h = phys_h, phys_w
    return MonitorGeometry(
        x=mon["x"], y=mon["y"],
        width=round(phys_w / scale), height=round(phys_h / scale),
        scale=scale,
    )


def _get_focused_monitor_x11() -> MonitorGeometry:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    display = Gdk.Display.get_default()
    seat = display.get_default_seat()
    pointer = seat.get_pointer()
    _screen, px, py = pointer.get_position()

    monitor = display.get_monitor_at_point(px, py)
    geo = monitor.get_geometry()
    return MonitorGeometry(
        x=geo.x, y=geo.y, width=geo.width, height=geo.height,
        scale=monitor.get_scale_factor(),
    )
