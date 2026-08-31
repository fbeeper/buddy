import json
import os
import tempfile
import unittest

import codex_buddy_hook


class CodexBuddyHookTests(unittest.TestCase):
    def make_cache_dir(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def make_index(self):
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(json.dumps({
            "id": "thr-1", "thread_name": "Initial name",
        }) + "\n")
        handle.write("not-json\n")
        handle.write(json.dumps({
            "id": "thr-1", "thread_name": "Renamed session",
        }) + "\n")
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name

    def make_transcript(self, reviewer, turn_id="turn-1", trailing_bytes=0):
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(json.dumps({
            "type": "turn_context",
            "payload": {
                "turn_id": turn_id,
                "approvals_reviewer": reviewer,
            },
        }) + "\n")
        if trailing_bytes:
            handle.write(json.dumps({"type": "noise", "payload": "x" * trailing_bytes}) + "\n")
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name

    def make_session_transcript(self, source):
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(json.dumps({
            "type": "session_meta",
            "payload": {"source": source},
        }) + "\n")
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name

    def test_native_events_map_to_canonical_states(self):
        expected = {
            "SessionStart": "idle",
            "UserPromptSubmit": "working",
            "PreToolUse": "working",
            "PostToolUse": "working",
            "PreCompact": "compacting",
            "PostCompact": "working",
            "Stop": "idle",
        }
        for native_event, state in expected.items():
            with self.subTest(native_event=native_event):
                event = codex_buddy_hook.harness_event({
                    "hook_event_name": native_event,
                    "session_id": "thr-1",
                    "cwd": "/tmp/project",
                }, "/missing", self.make_cache_dir())
                self.assertEqual(event.state, state)

    def test_auto_reviewed_permission_stays_working(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "PermissionRequest",
            "session_id": "thr-1",
            "turn_id": "turn-1",
            "transcript_path": self.make_transcript("auto_review"),
        }, "/missing", self.make_cache_dir())
        self.assertEqual(event.state, "working")

    def test_auto_reviewer_is_found_behind_a_long_turn(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "PermissionRequest",
            "session_id": "thr-1",
            "turn_id": "turn-1",
            "transcript_path": self.make_transcript("auto_review", trailing_bytes=1024 * 1024 + 1),
        }, "/missing", self.make_cache_dir())
        self.assertEqual(event.state, "working")

    def test_user_reviewed_permission_needs_approval(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "PermissionRequest",
            "session_id": "thr-1",
            "turn_id": "turn-1",
            "transcript_path": self.make_transcript("user"),
        }, "/missing", self.make_cache_dir())
        self.assertEqual(event.state, "approval")

    def test_unknown_permission_reviewer_fails_visible(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "PermissionRequest",
            "session_id": "thr-1",
        }, "/missing", self.make_cache_dir())
        self.assertEqual(event.state, "approval")

    def test_session_end_removes_the_row(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "SessionEnd",
            "session_id": "thr-1",
        }, cache_dir=self.make_cache_dir())
        self.assertEqual(event.operation, "end")

    def test_side_chat_stop_removes_ephemeral_row(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "Stop",
            "session_id": "side-chat",
            "transcript_path": self.make_session_transcript({
                "subagent": {"other": "guardian"},
            }),
        }, cache_dir=self.make_cache_dir())
        self.assertEqual(event.operation, "end")

    def test_main_session_stop_remains_idle(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "Stop",
            "session_id": "main-chat",
            "transcript_path": self.make_session_transcript("cli"),
        }, cache_dir=self.make_cache_dir())
        self.assertEqual(event.operation, "set")
        self.assertEqual(event.state, "idle")

    def test_latest_session_title_wins(self):
        index_path = self.make_index()
        label = codex_buddy_hook.display_label({
            "session_id": "thr-1",
            "cwd": "/tmp/project",
        }, index_path, self.make_cache_dir())
        self.assertEqual(label, "Renamed session")

    def test_prompt_then_cwd_are_label_fallbacks(self):
        missing = "/definitely/missing/session-index"
        cache_dir = self.make_cache_dir()
        self.assertEqual(codex_buddy_hook.display_label({
            "session_id": "unknown",
            "prompt": "  Build   the thing now  ",
            "cwd": "/tmp/project",
        }, missing, cache_dir), "Build the thing now")
        self.assertEqual(codex_buddy_hook.display_label({
            "session_id": "unknown",
            "cwd": "/tmp/project",
        }, missing, self.make_cache_dir()), "project")

    def test_prompt_label_survives_until_codex_indexes_a_title(self):
        cache_dir = self.make_cache_dir()
        missing = "/definitely/missing/session-index"
        working = codex_buddy_hook.harness_event({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "new-thread",
            "prompt": "Build the display adapter",
            "cwd": "/tmp/C",
        }, missing, cache_dir)
        stopped = codex_buddy_hook.harness_event({
            "hook_event_name": "Stop",
            "session_id": "new-thread",
            "cwd": "/tmp/C",
        }, missing, cache_dir)
        self.assertEqual(working.label, "Build the display adapter")
        self.assertEqual(stopped.label, working.label)

    def test_session_end_removes_cached_label(self):
        cache_dir = self.make_cache_dir()
        codex_buddy_hook.remember_label("thr-1", "Label", cache_dir)
        codex_buddy_hook.harness_event({
            "hook_event_name": "SessionEnd",
            "session_id": "thr-1",
        }, cache_dir=cache_dir)
        self.assertEqual(codex_buddy_hook.recalled_label("thr-1", cache_dir), "")

    def test_unrecognized_event_is_ignored(self):
        self.assertIsNone(codex_buddy_hook.harness_event({
            "hook_event_name": "SomethingFuture",
            "session_id": "thr-1",
        }, cache_dir=self.make_cache_dir()))

    def test_activity_arms_transcript_recovery(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "thr-1",
            "prompt": "Build it",
        }, "/missing", self.make_cache_dir())
        sent = []
        original_emit = codex_buddy_hook.buddy_harness.emit
        original_send = codex_buddy_hook.buddy_transport.send_line
        self.addCleanup(setattr, codex_buddy_hook.buddy_harness, "emit", original_emit)
        self.addCleanup(setattr, codex_buddy_hook.buddy_transport, "send_line", original_send)
        codex_buddy_hook.buddy_harness.emit = lambda value: sent.append(
            codex_buddy_hook.buddy_harness.relay_line(value))
        codex_buddy_hook.buddy_transport.send_line = sent.append

        codex_buddy_hook.dispatch({
            "hook_event_name": "UserPromptSubmit",
            "transcript_path": "/tmp/rollout.jsonl",
        }, event)

        self.assertEqual(
            sent[0],
            "SESSION codex-16398c9bc2a7 4CAF50 CO|Build : work",
        )
        self.assertEqual(
            sent[1],
            "WATCH codex-16398c9bc2a7 /tmp/rollout.jsonl codex Build it",
        )

    def test_stop_disarms_recovery_before_idle(self):
        event = codex_buddy_hook.harness_event({
            "hook_event_name": "Stop",
            "session_id": "thr-1",
            "cwd": "/tmp/project",
        }, "/missing", self.make_cache_dir())
        sent = []
        original_emit = codex_buddy_hook.buddy_harness.emit
        original_send = codex_buddy_hook.buddy_transport.send_line
        self.addCleanup(setattr, codex_buddy_hook.buddy_harness, "emit", original_emit)
        self.addCleanup(setattr, codex_buddy_hook.buddy_transport, "send_line", original_send)
        codex_buddy_hook.buddy_harness.emit = lambda value: sent.append("emit")
        codex_buddy_hook.buddy_transport.send_line = sent.append

        codex_buddy_hook.dispatch({"hook_event_name": "Stop"}, event)

        self.assertTrue(sent[0].startswith("UNWATCH codex-"))
        self.assertEqual(sent[1], "emit")


if __name__ == "__main__":
    unittest.main()
