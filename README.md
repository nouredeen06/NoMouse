# mouseoverlay

Keyboard-driven grid-click overlay for Hyprland and X11 — like macOS/iOS Voice
Control screen clicking, but keyboard controlled.

Runs as a background daemon. `mouseoverlay --show` pops up a numbered grid
overlay on the currently focused monitor. Type a cell number and press Enter
to zoom into it (3 stages, default 8x6 -> 4x3 -> 3x3); after the final stage,
Enter clicks the center of the chosen cell.

## Usage

```
mouseoverlay -d        # start the daemon in the background
mouseoverlay --show    # show the grid overlay
mouseoverlay --stop    # stop the daemon
mouseoverlay --status  # check whether the daemon is running
```

While the overlay is showing:

- Type digits + Enter: zoom into that cell (or click it, at the final stage).
- Enter with empty input: left-click the center of the current cell/region.
- `r` + Enter: right-click the center of the current cell/region.
- Digits + `r` + Enter (e.g. `5r`): right-click the center of that cell
  immediately, skipping any remaining zoom stages.
- Backspace on empty input: go back to the previous zoom stage.
- Escape: cancel, close the overlay without clicking.

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
[stage1]
cols = 8
rows = 6

[stage2]
cols = 4
rows = 3

[stage3]
cols = 3
rows = 3

background_rgba = "rgba(0, 0, 0, 0.35)"
```

Missing or malformed config falls back to the defaults shown above.
