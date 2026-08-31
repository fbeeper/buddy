import json
import unittest

import buddy_transcript


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


class BuddyTranscriptTests(unittest.TestCase):
    def test_claude_old_interrupt_field(self):
        self.assertEqual(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "user", "interruptedMessageId": "msg_123",
        })), "idle")

    def test_claude_current_interrupt_message(self):
        self.assertEqual(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "user",
            "message": {"role": "user", "content": [{
                "type": "text", "text": "[Request interrupted by user]",
            }]},
        })), "idle")

    def test_claude_tool_denial(self):
        self.assertEqual(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "user", "toolDenialKind": "user-rejected",
        })), "idle")

    def test_claude_terminal_api_failure(self):
        self.assertEqual(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "assistant", "isApiErrorMessage": True,
            "error": "rate_limit",
        })), "idle")

    def test_claude_retryable_api_failure_is_not_assumed_terminal(self):
        self.assertIsNone(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "assistant", "isApiErrorMessage": True,
            "error": "temporary_upstream_error",
        })))

    def test_quoted_marker_text_does_not_resolve(self):
        self.assertIsNone(buddy_transcript.resolution_for_line("claude", encoded({
            "type": "assistant",
            "message": {"role": "assistant", "content": (
                "Example: [Request interrupted by user] and interruptedMessageId"
            )},
        })))

    def test_profiles_are_isolated(self):
        codex_abort = encoded({
            "type": "event_msg",
            "payload": {"type": "turn_aborted", "reason": "interrupted"},
        })
        self.assertEqual(
            buddy_transcript.resolution_for_line("codex", codex_abort), "idle")
        self.assertIsNone(
            buddy_transcript.resolution_for_line("claude", codex_abort))

    def test_malformed_or_unknown_records_are_ignored(self):
        self.assertIsNone(buddy_transcript.resolution_for_line("claude", b"nope"))
        self.assertIsNone(buddy_transcript.resolution_for_line("unknown", b"{}"))


if __name__ == "__main__":
    unittest.main()
