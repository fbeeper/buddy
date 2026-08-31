#!/usr/bin/env python3
"""Device-wide configuration client for the Buddy display relay.

Use this for shared display settings and visual previews. Coding-harness
session lifecycle belongs in buddy_harness.py. This client talks only to the
relay's Unix socket and never opens the USB serial device.
"""

from __future__ import annotations

import argparse
import sys

import buddy_transport


class ConfigError(ValueError):
    """An invalid Buddy display configuration request."""


def clock_line(hour: int, minute: int, second: int, duration_s: float) -> str:
    """Build a temporary fake-time command; real host time resumes later."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ConfigError("hour must be 0-23, minute/second must be 0-59")
    if duration_s <= 0:
        raise ConfigError("duration must be positive")
    return f"CLOCK {hour} {minute} {second} {duration_s}"


def clock_style_line(style: str) -> str:
    """Build a persistent clock-visualization selection command."""
    if style not in ("arcs", "dots", "dotted-arcs"):
        raise ConfigError("clock style must be 'arcs', 'dots', or 'dotted-arcs'")
    return f"CSTYLE {style}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    buddy_transport.add_client_arguments(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    clock_parser = commands.add_parser(
        "clock", help="temporarily fake the device's decorative clock",
    )
    clock_parser.add_argument("hour", type=int, help="preview hour (0-23)")
    clock_parser.add_argument("minute", type=int, help="preview minute (0-59)")
    clock_parser.add_argument("second", type=int, help="preview second (0-59)")
    clock_parser.add_argument(
        "--duration", type=float, default=120.0,
        help="seconds before the relay resumes real time (default: 120)",
    )

    style_parser = commands.add_parser(
        "clock-style", help="select and persist the clock visualization",
    )
    style_parser.add_argument(
        "style", choices=("arcs", "dots", "dotted-arcs"),
        help="persistent clock visualization",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "clock":
            line = clock_line(args.hour, args.minute, args.second, args.duration)
        else:
            line = clock_style_line(args.style)
        buddy_transport.send_line(line, args.socket, args.timeout)
    except (ConfigError, OSError) as error:
        if not args.best_effort:
            print(f"buddy-config: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
