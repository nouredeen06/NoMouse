# mouseoverlay

Keyboard-driven grid-click overlay for Hyprland and X11 — like macOS/iOS Voice
Control screen clicking, but keyboard controlled.

Runs as a background daemon. `mouseoverlay --show` pops up a grid overlay on
the currently focused monitor. Each cell is labeled with a row digit (1-9)
and a column letter (a-p), e.g. `1a` or `9i`. Press the digit and letter keys
in either order — no Enter needed, it confirms as soon as both are set:

- Plain: left-click that cell's center.
- Hold **Shift** on the completing keystroke: zoom into that cell instead
  (up to 3 stages, each with a smaller grid).
- Hold **Ctrl** on the completing keystroke: right-click that cell's center.

## Usage

```
mouseoverlay -d        # start the daemon in the background
mouseoverlay --show    # show the grid overlay
mouseoverlay --stop    # stop the daemon
mouseoverlay --status  # check whether the daemon is running
```

While the overlay is showing:

- Type a digit or letter: highlights that row/column band; once both are
  set it fires immediately (see above for the Shift/Ctrl modifiers).
- Only one digit and one letter can be held at a time — a second press of
  an already-filled slot is ignored.
- Backspace: clears the most recently set digit/letter, or goes back one
  zoom stage if both are already empty.
- Enter with nothing typed: left-click the center of the current region
  (Ctrl+Enter right-clicks it).
- Escape: cancel, close the overlay without clicking.

A one-line hint fades out on its own after a couple seconds (or on the
first keystroke); set `show_hint = false` in the config to skip it
entirely and show no textbox at all.

## System prerequisites

These are system packages, not pip-installable:

- `gtk3`, `pygobject` (GObject introspection for GTK3)
- `gtk-layer-shell` (for the Hyprland/wlroots overlay layer surface)
- `xdotool` (click execution on X11)
- `ydotool` + a running `ydotoold` (click execution on Hyprland/Wayland —
  start `ydotoold` yourself, e.g. as a systemd user service; mouseoverlay
  does not start it for you)

## Install

```
pip install -e .
```

## Configuration

Optional config file at `~/.config/mouseoverlay/config.toml`:

```toml
background_rgba = "rgba(0, 0, 0, 0.35)"
show_hint = true
```

Missing or malformed config falls back to the defaults shown above. Grid
stage sizes (16x9 -> 4x3 -> 2x2) are fixed in this branch, not configurable.
