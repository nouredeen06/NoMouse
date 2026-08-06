"""Perform an actual mouse move/click at absolute screen coordinates."""

import logging
import subprocess
import time

log = logging.getLogger(__name__)

_X11_BUTTON = {"left": "1", "right": "3"}
_YDOTOOL_BUTTON = {"left": "0xC0", "right": "0xC1"}


def _hyprland_cursor_pos() -> tuple[int, int]:
    out = subprocess.run(
        ["hyprctl", "cursorpos"], capture_output=True, check=True, text=True,
    ).stdout.strip()
    x_str, y_str = out.split(",")
    return int(x_str.strip()), int(y_str.strip())


def move_to(backend: str, x: int, y: int) -> None:
    """Move the pointer to absolute screen coordinates (no click)."""
    x, y = int(x), int(y)
    if backend == "hyprland":
        _move_ydotool(x, y)
    else:
        _move_xdotool(x, y)


def press(backend: str, button: str = "left") -> None:
    """Press+release a mouse button at the pointer's current position."""
    if backend == "hyprland":
        subprocess.run(["ydotool", "click", _YDOTOOL_BUTTON[button]], check=True)
    else:
        subprocess.run(["xdotool", "click", _X11_BUTTON[button]], check=True)


def click(backend: str, x: int, y: int, button: str = "left") -> None:
    try:
        move_to(backend, x, y)
        press(backend, button)
    except FileNotFoundError as exc:
        tool = "ydotool" if backend == "hyprland" else "xdotool"
        log.error("%s not found: install it to enable clicking (%s)", tool, exc)
    except subprocess.CalledProcessError as exc:
        if backend == "hyprland":
            log.error("ydotool failed (is ydotoold running?): %s", exc)
        else:
            log.error("xdotool failed: %s", exc)


def _move_xdotool(x: int, y: int) -> None:
    subprocess.run(["xdotool", "mousemove", str(x), str(y)], check=True)


def _move_ydotool(x: int, y: int) -> None:
    # ydotool's --absolute mode needs ydotoold started with -T (touch device),
    # which is broken/exits immediately on some ydotool builds. Relative
    # movement works with ydotoold's default (mouse-only) EV_REL device, but
    # pointer acceleration curves make the actual distance moved diverge from
    # the requested delta (worse for large jumps). Damped convergence: halve
    # large deltas each step so it converges within a few ms regardless of
    # the active acceleration curve, and send small deltas (<=20px, ~1:1
    # accurate) as-is for a fast final snap. Whole loop runs in well under
    # 50ms, so it still reads as an instant jump rather than an animation.
    for _ in range(20):
        cur_x, cur_y = _hyprland_cursor_pos()
        dx, dy = x - cur_x, y - cur_y
        if abs(dx) <= 1 and abs(dy) <= 1:
            break
        send_x = dx if abs(dx) <= 20 else int(dx * 0.5)
        send_y = dy if abs(dy) <= 20 else int(dy * 0.5)
        subprocess.run(
            ["ydotool", "mousemove", "--", str(send_x), str(send_y)],
            check=True,
        )
        # hyprctl cursorpos can lag one compositor frame behind the move we
        # just sent; without a tiny settle delay the next read occasionally
        # comes back stale, making the loop think it converged one step
        # early and leaving a ~20px residual error.
        time.sleep(0.004)
