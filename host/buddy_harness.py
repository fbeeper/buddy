#!/usr/bin/env python3
"""Harness-neutral client for the buddy display relay.

This is the stable boundary coding-harness adapters should use. It accepts a
small versioned event vocabulary, applies the shared display policy, and
translates events to the relay's existing SESSION/END socket protocol.

It deliberately never opens the USB serial device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Mapping

import buddy_transport


PROTOCOL_VERSION = 1
MAX_LABEL_CHARS = 6

# State names are the public harness API. Colors and display words are policy
# owned here, not by individual harness adapters or the firmware.
STATE_STYLES = {
    "idle": ("3FAEDA", "idle"),
    "working": ("4CAF50", "work"),
    "waiting": ("80BB64", "wait"),
    "approval": ("D4301B", "appr"),
    "compacting": ("FDFB1D", "comp"),
    "error": ("AB47BC", "erro"),
}

HARNESS_RE = re.compile(r"^[A-Za-z0-9_.-]{1,24}$")
COLOR_RE = re.compile(r"^[0-9A-F]{6}$")


class EventError(ValueError):
    """An invalid harness event."""


@dataclass(frozen=True)
class HarnessEvent:
    operation: str
    harness: str
    session_id: str
    state: str | None = None
    label: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "HarnessEvent":
        version = value.get("v", value.get("version"))
        if version != PROTOCOL_VERSION:
            raise EventError(f"unsupported protocol version: {version!r}")

        operation = value.get("op")
        if operation not in ("set", "end"):
            raise EventError("op must be 'set' or 'end'")

        harness = value.get("harness")
        if not isinstance(harness, str) or not HARNESS_RE.fullmatch(harness):
            raise EventError("harness must match [A-Za-z0-9_.-]{1,24}")

        session_id = value.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise EventError("session_id must be a non-empty string")

        if operation == "end":
            return cls(operation, harness, session_id)

        state = value.get("state")
        if state not in STATE_STYLES:
            choices = ", ".join(STATE_STYLES)
            raise EventError(f"state must be one of: {choices}")

        label = value.get("label")
        if not isinstance(label, str) or not label.strip():
            raise EventError("label must be a non-empty string for op 'set'")

        return cls(operation, harness, session_id, state, clean_label(label))


def clean_label(label: str) -> str:
    """Make a user-provided label safe for the relay's line protocol."""
    return " ".join(label.split())[:64]


def harness_prefix(harness: str) -> str:
    """Two-letter tag shown before the label, derived from the harness id.

    No harness registers a prefix explicitly -- it's always the first two
    characters of the harness id, uppercased -- so a new adapter gets a
    reasonable tag automatically instead of needing a lookup table kept in
    sync here.
    """
    return harness[:2].upper()


def relay_id(harness: str, session_id: str) -> str:
    """Return a stable, whitespace-free, privacy-preserving relay id."""
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    test_prefix = "#" if session_id.startswith("#") else ""
    return f"{test_prefix}{harness}-{digest}"


def relay_line(event: HarnessEvent) -> str:
    logical_id = relay_id(event.harness, event.session_id)
    if event.operation == "end":
        return f"END {logical_id}"

    assert event.state is not None and event.label is not None
    color, word = STATE_STYLES[event.state]
    if not COLOR_RE.fullmatch(color):
        raise EventError(f"invalid configured color for {event.state}")
    prefix = harness_prefix(event.harness)
    text = f"{prefix}|{event.label[:MAX_LABEL_CHARS]}: {word}"
    return f"SESSION {logical_id} {color} {text}"


def alert_line(event: HarnessEvent) -> str:
    """Return the separate, backward-compatible attention update."""
    if event.operation != "set" or event.state is None:
        raise EventError("ALERT requires a set event")
    enabled = 1 if event.state == "approval" else 0
    return f"ALERT {relay_id(event.harness, event.session_id)} {enabled}"


def watch_line(event: HarnessEvent, transcript_path: str) -> str:
    """Arm relay-side recovery for lifecycle events a harness cannot expose."""
    if event.operation != "set" or event.label is None:
        raise EventError("WATCH requires a set event with a label")
    if not transcript_path or any(char.isspace() for char in transcript_path):
        raise EventError("transcript_path must be non-empty and contain no whitespace")
    logical_id = relay_id(event.harness, event.session_id)
    return f"WATCH {logical_id} {transcript_path} {event.harness} {event.label}"


def unwatch_line(event: HarnessEvent) -> str:
    """Disarm relay-side transcript recovery for a session."""
    return f"UNWATCH {relay_id(event.harness, event.session_id)}"


def emit(
    event: HarnessEvent,
    socket_path: str = buddy_transport.DEFAULT_SOCKET,
    timeout: float = buddy_transport.DEFAULT_TIMEOUT_SECONDS,
) -> None:
    buddy_transport.send_line(relay_line(event), socket_path, timeout)
    if event.operation == "set":
        buddy_transport.send_line(alert_line(event), socket_path, timeout)


def parse_json_event(stream: Any) -> HarnessEvent:
    try:
        value = json.load(stream)
    except (OSError, ValueError) as error:
        raise EventError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise EventError("event must be a JSON object")
    return HarnessEvent.from_mapping(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    buddy_transport.add_client_arguments(parser)

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("json", help="read one versioned event object from stdin")

    set_parser = commands.add_parser("set", help="create or update a session")
    set_parser.add_argument("harness", help="stable producer name, e.g. codex")
    set_parser.add_argument("session_id", help="stable native session id")
    set_parser.add_argument("state", choices=STATE_STYLES,
                            help="canonical lifecycle state")
    set_parser.add_argument("label", help="short human-readable display label")

    end_parser = commands.add_parser("end", help="remove a session")
    end_parser.add_argument("harness", help="same producer name used by set")
    end_parser.add_argument("session_id", help="same native id used by set")

    demo_parser = commands.add_parser("demo", help="cycle a temporary row through states")
    demo_parser.add_argument(
        "--delay", type=float, default=0.8,
        help="seconds to show each state (default: 0.8)",
    )

    return parser


def event_from_args(args: argparse.Namespace) -> HarnessEvent:
    if args.command == "json":
        return parse_json_event(sys.stdin)
    if args.command == "set":
        return HarnessEvent.from_mapping({
            "v": 1,
            "op": "set",
            "harness": args.harness,
            "session_id": args.session_id,
            "state": args.state,
            "label": args.label,
        })
    if args.command == "end":
        return HarnessEvent.from_mapping({
            "v": 1,
            "op": "end",
            "harness": args.harness,
            "session_id": args.session_id,
        })
    raise EventError(f"unsupported command: {args.command}")


def run_demo(args: argparse.Namespace) -> None:
    base = {"v": 1, "harness": "sample", "session_id": "#demo"}
    try:
        for state in ("idle", "working", "approval", "compacting", "error"):
            event = HarnessEvent.from_mapping({
                **base, "op": "set", "state": state, "label": "#demo",
            })
            emit(event, args.socket, args.timeout)
            time.sleep(max(0.0, args.delay))
    finally:
        emit(
            HarnessEvent.from_mapping({**base, "op": "end"}),
            args.socket,
            args.timeout,
        )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "demo":
            run_demo(args)
        else:
            emit(event_from_args(args), args.socket, args.timeout)
    except (EventError, OSError) as error:
        if not args.best_effort:
            print(f"buddy-harness: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
