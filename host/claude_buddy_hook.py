#!/usr/bin/env python3
"""Translate Claude Code lifecycle hooks to the shared buddy harness API.

Claude-specific policy is deliberately limited to native event mapping,
session-name discovery, and deciding when transcript recovery is armed. The
shared harness layer owns display styling, private relay ids, and lifecycle
protocol construction; buddy_transport owns the socket write.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any, Mapping

sys.path.insert(0, os.path.expanduser("~/.local/share/buddy-display"))
import buddy_harness
import buddy_transport


SESSIONS_REGISTRY_GLOB = os.path.expanduser("~/.claude/sessions/*.json")

EVENT_STATES = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PermissionRequest": "approval",
    "PermissionDenied": "idle",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "PreCompact": "compacting",
    "PostCompact": "working",
    "Stop": "idle",
}

WATCH_EVENTS = {
    "UserPromptSubmit",
    "PermissionRequest",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
}


def registry_name(
    session_id: str,
    registry_glob: str = SESSIONS_REGISTRY_GLOB,
) -> str:
    """Return Claude Code's current user-facing name for a session."""
    for path in glob.glob(registry_glob):
        try:
            with open(path, encoding="utf-8") as registry:
                entry = json.load(registry)
        except (OSError, ValueError):
            continue
        if entry.get("sessionId") == session_id:
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                return name
    return ""


def prompt_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:32]


def display_label(
    payload: Mapping[str, Any],
    registry_glob: str = SESSIONS_REGISTRY_GLOB,
) -> str:
    session_id = payload.get("session_id")
    if isinstance(session_id, str):
        name = registry_name(session_id, registry_glob)
        if name:
            return buddy_harness.clean_label(name)

    user_input = payload.get("user_input")
    if isinstance(user_input, str) and user_input.strip():
        return buddy_harness.clean_label(prompt_title(user_input))

    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        basename = os.path.basename(cwd.rstrip(os.sep))
        if basename:
            return buddy_harness.clean_label(basename)

    if isinstance(session_id, str) and session_id:
        return session_id.replace("-", "")[:8]
    return "claude"


def harness_event(
    payload: Mapping[str, Any],
    registry_glob: str = SESSIONS_REGISTRY_GLOB,
) -> buddy_harness.HarnessEvent | None:
    event_name = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None

    if event_name == "SessionEnd":
        return buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "end",
            "harness": "claude",
            "session_id": session_id,
        })

    state = EVENT_STATES.get(event_name)
    if state is None:
        return None

    return buddy_harness.HarnessEvent.from_mapping({
        "v": 1,
        "op": "set",
        "harness": "claude",
        "session_id": session_id,
        "state": state,
        "label": display_label(payload, registry_glob),
    })


def dispatch(payload: Mapping[str, Any], event: buddy_harness.HarnessEvent) -> None:
    event_name = payload.get("hook_event_name")
    if event_name in ("PermissionDenied", "Stop", "SessionEnd"):
        buddy_transport.send_line(buddy_harness.unwatch_line(event))

    buddy_harness.emit(event)

    transcript_path = payload.get("transcript_path")
    if event_name in WATCH_EVENTS and isinstance(transcript_path, str):
        buddy_transport.send_line(buddy_harness.watch_line(event, transcript_path))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            event = harness_event(payload)
            if event is not None:
                dispatch(payload, event)
    except Exception:
        # The display is decorative. It must never block or fail Claude Code.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
