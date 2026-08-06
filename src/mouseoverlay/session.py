"""Detect which display-server backend we're running under."""

import os


def get_backend_name() -> str:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        return "x11"
    return "x11"
