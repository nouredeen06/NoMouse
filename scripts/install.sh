#!/bin/sh
# Install NoMouse and its system prerequisites, then pip-install the package.
#
# Usage: scripts/install.sh
#
# Safe to re-run: only installs what's missing, and pip install -e is
# idempotent.

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> checking system prerequisites"

MISSING_PACMAN=""
have_cmd() { command -v "$1" >/dev/null 2>&1; }
have_python_module() { python3 -c "import $1" >/dev/null 2>&1; }

have_cmd xdotool || MISSING_PACMAN="$MISSING_PACMAN xdotool"
have_cmd ydotool || MISSING_PACMAN="$MISSING_PACMAN ydotool"
have_python_module gi || MISSING_PACMAN="$MISSING_PACMAN python-gobject gtk3"

if python3 -c "import gi; gi.require_version('GtkLayerShell', '0.1'); from gi.repository import GtkLayerShell" >/dev/null 2>&1; then
    :
else
    MISSING_PACMAN="$MISSING_PACMAN gtk-layer-shell"
fi

if [ -n "$MISSING_PACMAN" ]; then
    if have_cmd pacman; then
        echo "==> installing missing packages via pacman:$MISSING_PACMAN"
        sudo pacman -S --needed $MISSING_PACMAN
    else
        echo "missing prerequisites:$MISSING_PACMAN" >&2
        echo "this script only automates installation on Arch (pacman)." >&2
        echo "on other distros, install the equivalents of: gtk3, gobject-introspection/python-gobject, gtk-layer-shell, xdotool, ydotool - see README.md prerequisites." >&2
        exit 1
    fi
else
    echo "==> all system prerequisites already present"
fi

echo "==> installing the nomouse package"
if python3 -m pip install -e "$ROOT" 2>/dev/null; then
    :
else
    # PEP 668 externally-managed environments (most distro python installs)
    # need this flag for a user-level editable install.
    python3 -m pip install -e "$ROOT" --break-system-packages
fi

if have_cmd systemctl && [ -f /usr/lib/systemd/user/ydotool.service ]; then
    if ! systemctl --user is-active --quiet ydotool.service; then
        echo "==> enabling ydotoold (needed for clicks on Hyprland/Wayland)"
        systemctl --user enable --now ydotool.service
    fi
fi

echo
echo "==> done. try it:"
echo "    nomouse -d        # start the daemon"
echo "    nomouse --show    # show the grid overlay"
