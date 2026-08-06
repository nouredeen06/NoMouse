"""Daemon: owns the GTK main loop, listens for IPC commands in a background thread."""

import logging

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from nomouse import ipc, session
from nomouse.clicker import click
from nomouse.config import Config, load_config
from nomouse.monitors import get_focused_monitor
from nomouse.overlay import OverlayWindow

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config: Config):
        self.config = config
        self.backend_name = session.get_backend_name()
        self.overlay_window: OverlayWindow | None = None
        log.info("backend: %s", self.backend_name)

    def run(self) -> None:
        ipc.serve(self._handle_command)
        Gtk.main()

    def _handle_command(self, cmd: str) -> str:
        if cmd == "PING":
            return "PONG"
        if cmd == "SHOW":
            GLib.idle_add(self._show_overlay)
            return "OK"
        if cmd == "STOP":
            GLib.idle_add(Gtk.main_quit)
            return "OK"
        return f"ERR: unknown command {cmd!r}"

    def _show_overlay(self) -> bool:
        if self.overlay_window is not None:
            log.info("overlay already showing, ignoring SHOW")
            return False
        try:
            monitor = get_focused_monitor(self.backend_name)
        except Exception:
            log.exception("failed to determine focused monitor")
            return False

        win = OverlayWindow(monitor, self.config, self.backend_name, click)
        win.connect("destroy", self._on_overlay_destroy)
        self.overlay_window = win
        win.show_all_and_focus()
        return False

    def _on_overlay_destroy(self, _widget) -> None:
        self.overlay_window = None


def run_daemon(config: Config | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config is None:
        config = load_config()
    Daemon(config).run()
