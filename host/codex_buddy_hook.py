#!/usr/bin/env python3
"""Map Codex lifecycle-hook payloads to the buddy harness event contract.

The hook is intentionally best-effort: display failures never block Codex.
It always emits an empty JSON object on stdout because Codex Stop hooks require
valid JSON when they exit successfully.
"""

from __future__ import annotations

import json
import os
import re
import sys
import hashlib
from typing import Any, Mapping

sys.path.insert(0, os.path.expanduser("~/.local/share/buddy-display"))
import buddy_harness
import buddy_transport


SESSION_INDEX_PATH = os.path.expanduser("~/.codex/session_index.jsonl")
LABEL_CACHE_DIR = os.path.expanduser("~/.codex/buddy-labels")

EVENT_STATES = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "PreCompact": "compacting",
    "PostCompact": "idle",
    "Stop": "idle",
}

WATCH_EVENTS = {
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "PreCompact",
}


def session_title(session_id: str, index_path: str = SESSION_INDEX_PATH) -> str:
    """Best-effort lookup of Codex's current user-facing conversation title."""
    title = ""
    try:
        with open(index_path, encoding="utf-8") as index:
            for line in index:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("id") == session_id:
                    candidate = entry.get("thread_name")
                    if isinstance(candidate, str) and candidate.strip():
                        title = candidate
    except OSError:
        pass
    return title


def prompt_title(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", prompt).strip()
    return cleaned[:32]


def label_cache_path(session_id: str, cache_dir: str = LABEL_CACHE_DIR) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, digest)


def remember_label(
    session_id: str,
    label: str,
    cache_dir: str = LABEL_CACHE_DIR,
) -> str:
    label = buddy_harness.clean_label(label)
    try:
        os.makedirs(cache_dir, mode=0o700, exist_ok=True)
        path = label_cache_path(session_id, cache_dir)
        with open(path, "w", encoding="utf-8") as cache:
            cache.write(label)
        os.chmod(path, 0o600)
    except OSError:
        pass
    return label


def recalled_label(session_id: str, cache_dir: str = LABEL_CACHE_DIR) -> str:
    try:
        with open(label_cache_path(session_id, cache_dir), encoding="utf-8") as cache:
            return buddy_harness.clean_label(cache.read())
    except OSError:
        return ""


def forget_label(session_id: str, cache_dir: str = LABEL_CACHE_DIR) -> None:
    try:
        os.unlink(label_cache_path(session_id, cache_dir))
    except OSError:
        pass


def permission_state(payload: Mapping[str, Any]) -> str:
    """Keep auto-reviewed escalations working; expose only user decisions."""
    transcript_path = payload.get("transcript_path")
    turn_id = payload.get("turn_id")
    if not isinstance(transcript_path, str) or not isinstance(turn_id, str):
        return "approval"

    try:
        with open(transcript_path, "rb") as transcript:
            transcript.seek(0, os.SEEK_END)
            position = transcript.tell()
            remainder = b""
            while position:
                size = min(64 * 1024, position)
                position -= size
                transcript.seek(position)
                parts = (transcript.read(size) + remainder).split(b"\n")
                remainder = parts[0]
                for raw_line in reversed(parts[1:]):
                    try:
                        record = json.loads(raw_line)
                    except (TypeError, ValueError):
                        continue
                    if record.get("type") != "turn_context":
                        continue
                    context = record.get("payload")
                    if not isinstance(context, dict) or context.get("turn_id") != turn_id:
                        continue
                    return "working" if context.get("approvals_reviewer") == "auto_review" else "approval"

            if remainder:
                try:
                    record = json.loads(remainder)
                except (TypeError, ValueError):
                    record = None
                if isinstance(record, dict) and record.get("type") == "turn_context":
                    context = record.get("payload")
                    if isinstance(context, dict) and context.get("turn_id") == turn_id:
                        return "working" if context.get("approvals_reviewer") == "auto_review" else "approval"
    except OSError:
        return "approval"

    # If Codex changes its transcript schema, fail visibly instead of hiding
    # an interaction that may genuinely require the user.
    return "approval"


def is_ephemeral_subagent(payload: Mapping[str, Any]) -> bool:
    """Return whether this transcript belongs to a Codex side-chat/subagent."""
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str):
        return False
    try:
        with open(transcript_path, "rb") as transcript:
            record = json.loads(transcript.readline())
    except (OSError, TypeError, ValueError):
        return False
    if record.get("type") != "session_meta":
        return False
    metadata = record.get("payload")
    return isinstance(metadata, dict) and isinstance(metadata.get("source"), dict) \
        and "subagent" in metadata["source"]


def display_label(
    payload: Mapping[str, Any],
    index_path: str = SESSION_INDEX_PATH,
    cache_dir: str = LABEL_CACHE_DIR,
) -> str:
    session_id = payload.get("session_id", "")
    if isinstance(session_id, str):
        title = session_title(session_id, index_path)
        if title:
            return remember_label(session_id, title, cache_dir)

    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return remember_label(session_id, prompt_title(prompt), cache_dir)

    if isinstance(session_id, str):
        cached = recalled_label(session_id, cache_dir)
        if cached:
            return cached

    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        basename = os.path.basename(cwd.rstrip(os.sep))
        if basename:
            if isinstance(session_id, str):
                return remember_label(session_id, basename, cache_dir)
            return basename

    return "codex"


def harness_event(
    payload: Mapping[str, Any],
    index_path: str = SESSION_INDEX_PATH,
    cache_dir: str = LABEL_CACHE_DIR,
) -> buddy_harness.HarnessEvent | None:
    event_name = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None

    if event_name == "SessionEnd":
        forget_label(session_id, cache_dir)
        return buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "end",
            "harness": "codex",
            "session_id": session_id,
        })

    # Codex side chats/subagents currently emit Stop when their task finishes
    # but no SessionEnd when their panel is closed. Treat them as ephemeral so
    # completed side work cannot leave an idle row behind indefinitely.
    if event_name == "Stop" and is_ephemeral_subagent(payload):
        forget_label(session_id, cache_dir)
        return buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "end",
            "harness": "codex",
            "session_id": session_id,
        })

    state = permission_state(payload) if event_name == "PermissionRequest" else EVENT_STATES.get(event_name)
    if state is None:
        return None

    return buddy_harness.HarnessEvent.from_mapping({
        "v": 1,
        "op": "set",
        "harness": "codex",
        "session_id": session_id,
        "state": state,
        "label": display_label(payload, index_path, cache_dir),
    })


def dispatch(payload: Mapping[str, Any], event: buddy_harness.HarnessEvent) -> None:
    """Emit state and maintain transcript recovery around active Codex turns."""
    event_name = payload.get("hook_event_name")

    # Clear first so an already-written abort marker cannot resurrect an ended
    # row after END or race a normal Stop update.
    if event_name in ("PostCompact", "Stop", "SessionEnd"):
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
        # This is a decorative, out-of-band status integration. A malformed
        # payload, missing index, stopped relay, or unplugged board must never
        # break or delay the actual coding session.
        pass

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
