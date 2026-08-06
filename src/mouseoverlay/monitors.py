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
        for mon in monitors:
            if mon.get("focused"):
                return MonitorGeometry(
                    x=mon["x"], y=mon["y"],
                    width=mon["width"], height=mon["height"],
                    scale=mon.get("scale", 1.0),
                )
        log.warning("hyprctl monitors: no focused monitor found, using first")
        mon = monitors[0]
        return MonitorGeometry(
            x=mon["x"], y=mon["y"], width=mon["width"], height=mon["height"],
            scale=mon.get("scale", 1.0),
        )
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, IndexError, KeyError) as exc:
        log.error("failed to query hyprctl monitors: %s", exc)
        raise


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
