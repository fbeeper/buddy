import json
import os
import tempfile
import unittest

import claude_buddy_hook


class ClaudeBuddyHookTests(unittest.TestCase):
    def make_registry(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "session.json")
        with open(path, "w", encoding="utf-8") as registry:
            json.dump({"sessionId": "claude-1", "name": "Named session"}, registry)
        return os.path.join(directory.name, "*.json")

    def test_native_events_map_to_canonical_states(self):
        expected = {
            "SessionStart": "idle",
            "UserPromptSubmit": "working",
            "PermissionRequest": "approval",
            "PermissionDenied": "idle",
            "PreToolUse": "working",
            "PostToolUse": "working",
            "PreCompact": "compacting",
            "PostCompact": "idle",
            "Stop": "idle",
        }
        for native_event, state in expected.items():
            with self.subTest(native_event=native_event):
                event = claude_buddy_hook.harness_event({
                    "hook_event_name": native_event,
                    "session_id": "claude-1",
                    "cwd": "/tmp/project",
                }, "/missing/*.json")
                self.assertEqual(event.state, state)

    def test_session_end_uses_shared_end_contract(self):
        event = claude_buddy_hook.harness_event({
            "hook_event_name": "SessionEnd",
            "session_id": "claude-1",
        })
        self.assertEqual(event.operation, "end")
        self.assertTrue(claude_buddy_hook.buddy_harness.relay_line(event).startswith("END claude-"))

    def test_registry_name_then_prompt_then_cwd(self):
        registry_glob = self.make_registry()
        self.assertEqual(claude_buddy_hook.display_label({
            "session_id": "claude-1", "user_input": "Prompt", "cwd": "/tmp/project",
        }, registry_glob), "Named session")
        self.assertEqual(claude_buddy_hook.display_label({
            "session_id": "missing", "user_input": "  Build   this now ",
        }, registry_glob), "Build this now")
        self.assertEqual(claude_buddy_hook.display_label({
            "session_id": "missing", "cwd": "/tmp/project",
        }, registry_glob), "project")

    def test_permission_request_uses_approval_style_and_arms_watch(self):
        event = claude_buddy_hook.harness_event({
            "hook_event_name": "PermissionRequest",
            "session_id": "claude-1",
            "cwd": "/tmp/project",
        }, "/missing/*.json")
        sent = []
        original_emit = claude_buddy_hook.buddy_harness.emit
        original_send = claude_buddy_hook.buddy_transport.send_line
        self.addCleanup(setattr, claude_buddy_hook.buddy_harness, "emit", original_emit)
        self.addCleanup(setattr, claude_buddy_hook.buddy_transport, "send_line", original_send)
        claude_buddy_hook.buddy_harness.emit = lambda value: sent.append(
            claude_buddy_hook.buddy_harness.relay_line(value))
        claude_buddy_hook.buddy_transport.send_line = sent.append

        claude_buddy_hook.dispatch({
            "hook_event_name": "PermissionRequest",
            "transcript_path": "/tmp/claude.jsonl",
        }, event)

        self.assertIn(" D4301B CL|projec: appr", sent[0])
        self.assertTrue(sent[1].startswith("WATCH claude-"))

    def test_stop_unwatches_before_idle(self):
        event = claude_buddy_hook.harness_event({
            "hook_event_name": "Stop",
            "session_id": "claude-1",
            "cwd": "/tmp/project",
        }, "/missing/*.json")
        sent = []
        original_emit = claude_buddy_hook.buddy_harness.emit
        original_send = claude_buddy_hook.buddy_transport.send_line
        self.addCleanup(setattr, claude_buddy_hook.buddy_harness, "emit", original_emit)
        self.addCleanup(setattr, claude_buddy_hook.buddy_transport, "send_line", original_send)
        claude_buddy_hook.buddy_harness.emit = lambda value: sent.append("emit")
        claude_buddy_hook.buddy_transport.send_line = sent.append

        claude_buddy_hook.dispatch({"hook_event_name": "Stop"}, event)

        self.assertTrue(sent[0].startswith("UNWATCH claude-"))
        self.assertEqual(sent[1], "emit")


if __name__ == "__main__":
    unittest.main()
