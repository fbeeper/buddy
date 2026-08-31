"""Shared local-socket transport for Buddy host clients.

This module is deliberately ignorant of sessions, clock styles, and firmware.
It sends one newline-terminated command to the persistent relay and never opens
the USB serial device.
"""

from __future__ import annotations

import argparse
import os
import socket


DEFAULT_SOCKET = os.path.expanduser("~/.local/share/buddy-display/buddy-relay.sock")
DEFAULT_TIMEOUT_SECONDS = 0.3


def add_client_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the common relay connection options to a top-level CLI parser."""
    parser.add_argument("--socket", default=DEFAULT_SOCKET, help="relay Unix socket")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
        help="socket timeout in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--best-effort", action="store_true",
        help="exit successfully if the relay is unavailable (recommended for hooks)",
    )


def send_line(
    line: str,
    socket_path: str = DEFAULT_SOCKET,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    payload = (line + "\n").encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(os.path.expanduser(socket_path))
        client.sendall(payload)
