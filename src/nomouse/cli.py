"""nomouse CLI: start the daemon, or send it commands."""

import argparse
import logging
import os
import sys
from pathlib import Path

from nomouse import ipc

log = logging.getLogger(__name__)


def _log_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    d = Path(state_home) / "nomouse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _start_daemon() -> None:
    if ipc.is_daemon_running():
        print("nomouse daemon is already running", file=sys.stderr)
        sys.exit(1)

    import subprocess

    log_path = _log_dir() / "daemon.log"
    log_file = open(log_path, "a")
    subprocess.Popen(
        [sys.executable, "-m", "nomouse.cli", "--foreground-daemon"],
        stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"nomouse daemon started (log: {log_path})")


def _run_foreground_daemon() -> None:
    from nomouse.daemon import run_daemon
    run_daemon()


def _send(cmd: str) -> None:
    try:
        reply = ipc.send_command(cmd)
    except OSError:
        print("nomouse daemon is not running (start it with -d)", file=sys.stderr)
        sys.exit(1)
    if reply.startswith("ERR"):
        print(reply, file=sys.stderr)
        sys.exit(1)


def _status() -> None:
    if ipc.is_daemon_running():
        print("nomouse daemon is running")
    else:
        print("nomouse daemon is not running")
        sys.exit(1)


def _run_sequence(numbers: list[int], button: str = "left") -> None:
    """Non-interactively resolve a sequence of grid picks and click there.

    Bypasses the daemon/overlay entirely: no window is shown, no daemon
    needs to be running. Useful for scripting and for the accuracy test.
    """
    from nomouse import session
    from nomouse.clicker import click
    from nomouse.config import load_config
    from nomouse.grid import resolve_region
    from nomouse.monitors import get_focused_monitor

    backend = session.get_backend_name()
    config = load_config()
    monitor = get_focused_monitor(backend)

    try:
        region = resolve_region(monitor, config, numbers)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    cx, cy = region.center()
    click(backend, cx, cy, button)


def main() -> None:
    parser = argparse.ArgumentParser(prog="nomouse")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-d", "--daemon", action="store_true", help="start the daemon in the background")
    group.add_argument("--foreground-daemon", action="store_true", help=argparse.SUPPRESS)
    group.add_argument("--show", action="store_true", help="show the grid overlay on the focused monitor")
    group.add_argument("--stop", action="store_true", help="stop the running daemon")
    group.add_argument("--status", action="store_true", help="check whether the daemon is running")
    group.add_argument(
        "--run", nargs="+", type=int, metavar="N",
        help="non-interactively pick grid cells (1-3 numbers, one per stage) and click, e.g. --run 20 9 2",
    )
    parser.add_argument(
        "--right", action="store_true",
        help="with --run, right-click instead of left-click",
    )

    args = parser.parse_args()

    if args.daemon:
        _start_daemon()
    elif args.foreground_daemon:
        _run_foreground_daemon()
    elif args.show:
        _send("SHOW")
    elif args.stop:
        _send("STOP")
    elif args.status:
        _status()
    elif args.run is not None:
        _run_sequence(args.run, "right" if args.right else "left")


if __name__ == "__main__":
    main()
