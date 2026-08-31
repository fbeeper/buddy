"""Harness-specific transcript fallbacks for missing lifecycle hooks.

This module is intentionally separate from the relay. Transcript JSONL is an
unstable implementation detail of each harness; the relay only asks this
module whether a complete appended record represents a terminal turn outcome.
Native lifecycle hooks remain authoritative whenever they exist.
"""

from __future__ import annotations

import json
from typing import Any


CLAUDE_INTERRUPT_TEXTS = (
    "[Request interrupted by user]",
    "[Request interrupted by user for tool use]",
)


def _claude_resolution(entry: dict[str, Any]) -> str | None:
    # These are top-level lifecycle fields in real Claude transcript records.
    # Looking only at top level prevents quoted diagnostics/tool output from
    # accidentally resolving an active turn.
    if entry.get("toolDenialKind"):
        return "idle"
    if entry.get("interruptedMessageId"):
        return "idle"

    # Claude 2.1.250 can omit interruptedMessageId and emit only this exact,
    # synthetic user record when Escape cancels a turn.
    if entry.get("type") == "user":
        message = entry.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                texts = (content,)
            elif isinstance(content, list):
                texts = tuple(
                    item.get("text")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                texts = ()
            if any(text in CLAUDE_INTERRUPT_TEXTS for text in texts):
                return "idle"

    # Demonstrated quota/session-limit failures do not reliably produce Stop.
    # Keep this deliberately narrower than "any API error": transient errors
    # may be retried automatically and must not make real work look idle.
    if entry.get("type") == "assistant" and entry.get("isApiErrorMessage") is True:
        quota = entry.get("quotaLimits")
        quota_rejected = isinstance(quota, dict) and quota.get("status") == "rejected"
        if entry.get("error") == "rate_limit" or quota_rejected:
            return "idle"

    return None


def _codex_resolution(entry: dict[str, Any]) -> str | None:
    if entry.get("type") != "event_msg":
        return None
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") == "turn_aborted" and payload.get("reason") == "interrupted":
        return "idle"
    return None


def resolution_for_line(profile: str, line: bytes) -> str | None:
    """Return the canonical terminal state represented by one JSONL record."""
    try:
        entry = json.loads(line)
    except (TypeError, ValueError):
        return None
    if not isinstance(entry, dict):
        return None

    if profile == "claude":
        return _claude_resolution(entry)
    if profile == "codex":
        return _codex_resolution(entry)
    if profile == "auto":
        return _claude_resolution(entry) or _codex_resolution(entry)
    return None
