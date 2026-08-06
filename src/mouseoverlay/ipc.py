"""Unix domain socket IPC between the CLI client and the daemon."""

import logging
import os
import socket
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


def socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / "mouseoverlay.sock"


def send_command(cmd: str, timeout: float = 3.0) -> str:
    path = socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        sock.sendall((cmd + "\n").encode())
        reply = sock.recv(4096).decode().strip()
    return reply


def is_daemon_running() -> bool:
    try:
        return send_command("PING") == "PONG"
    except OSError:
        return False


def _bind_socket() -> socket.socket:
    path = socket_path()

    if path.exists():
        if is_daemon_running():
            raise RuntimeError(f"daemon already running (socket {path} is live)")
        path.unlink()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(5)
    return sock


def serve(handler: Callable[[str], str]) -> threading.Thread:
    """Bind the socket and run the accept loop in a background thread."""
    sock = _bind_socket()

    def _accept_loop() -> None:
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            with conn:
                try:
                    data = conn.recv(4096).decode().strip()
                    if not data:
                        continue
                    reply = handler(data)
                    conn.sendall((reply + "\n").encode())
                except OSError as exc:
                    log.warning("ipc connection error: %s", exc)

    thread = threading.Thread(target=_accept_loop, daemon=True, name="ipc-accept-loop")
    thread.start()
    return thread
