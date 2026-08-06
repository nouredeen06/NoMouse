<p align="center">
  <img src="assets/nomouse.jpeg" alt="NoMouse" width="360">
</p>

# NoMouse

Keyboard-driven grid-click overlay for Hyprland and X11. Runs as a
background daemon; a keypress pops up a grid on the focused monitor and you
click by typing a cell's row+column label instead of moving a mouse.

## Prerequisites

System packages (not pip-installable):

- `gtk3`, `python-gobject` (GObject introspection for GTK3)
- `gtk-layer-shell` (for the Hyprland/wlroots overlay layer surface)
- `xdotool` (click execution on X11)
- `ydotool` + a running `ydotoold` (click execution on Hyprland/Wayland)

Plus Python 3.11+.

## Install

```
git clone https://github.com/nouredeen06/NoMouse.git
cd NoMouse
scripts/install.sh
```

`scripts/install.sh` installs the missing system prerequisites via `pacman`
(Arch only — on other distros, install the equivalents listed above
manually first), pip-installs the package in editable mode, and enables the
`ydotoold` user service if it isn't already running. Safe to re-run any time
you pull new changes.

## Usage

```
nomouse -d        # start the daemon in the background
nomouse --show    # show the grid overlay
nomouse --stop    # stop the daemon
nomouse --status  # check whether the daemon is running
```

`nomouse --show` pops up a grid overlay on the currently focused monitor.
Each cell is labeled with a row digit (1-9) and a column letter (a-p), e.g.
`1a` or `9i`. Press the digit and letter keys in either order — no Enter
needed, it confirms as soon as both are set:

- Plain: left-click that cell's center.
- Hold **Shift** on the completing keystroke: zoom into that cell instead
  (up to 3 stages, each with a smaller grid).
- Hold **Ctrl** on the completing keystroke: right-click that cell's center.

Other controls while the overlay is showing:

- Type a digit or letter: highlights that row/column band before the pair
  is complete.
- Only one digit and one letter can be held at a time — a second press of
  an already-filled slot is ignored.
- Backspace: clears the most recently set digit/letter, or goes back one
  zoom stage if both are already empty.
- Enter with nothing typed: left-click the center of the current region
  (Ctrl+Enter right-clicks it).
- Escape: cancel, close the overlay without clicking.

A one-line hint fades in/out on its own after a couple seconds (or on the
first keystroke, whichever comes first) — see `show_hint` below to disable
it entirely.

Multi-monitor: the overlay always shows on the currently focused monitor.

## Configuration

Optional config file at `~/.config/nomouse/config.toml`:

```toml
background_rgba = "rgba(0, 0, 0, 0.35)"
show_hint = true
```

Missing or malformed config falls back to the defaults shown above. Grid
stage sizes (16x9 -> 4x3 -> 2x2) are fixed, not configurable.
