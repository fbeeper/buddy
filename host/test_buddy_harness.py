import io
import unittest

import buddy_harness


class BuddyHarnessTests(unittest.TestCase):
    def test_status_palette(self):
        self.assertEqual(buddy_harness.STATE_STYLES["approval"][0], "D4301B")
        self.assertEqual(buddy_harness.STATE_STYLES["waiting"][0], "80BB64")
        self.assertEqual(buddy_harness.STATE_STYLES["compacting"][0], "FDFB1D")
        self.assertEqual(buddy_harness.STATE_STYLES["idle"][0], "3FAEDA")

    def test_set_event_translates_to_legacy_relay_protocol(self):
        event = buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "set",
            "harness": "codex",
            "session_id": "thread with private text",
            "state": "approval",
            "label": "round-display",
        })
        line = buddy_harness.relay_line(event)
        self.assertRegex(
            line,
            r"^SESSION codex-[0-9a-f]{12} D4301B CO\|round-: appr$",
        )
        self.assertNotIn("private", line)

    def test_end_uses_same_stable_id(self):
        set_event = buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "set",
            "harness": "claude",
            "session_id": "abc",
            "state": "working",
            "label": "project",
        })
        end_event = buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "end",
            "harness": "claude",
            "session_id": "abc",
        })
        set_id = buddy_harness.relay_line(set_event).split()[1]
        self.assertEqual(buddy_harness.relay_line(end_event), f"END {set_id}")

    def test_alert_is_separate_and_only_approval_enables_it(self):
        for state in buddy_harness.STATE_STYLES:
            event = buddy_harness.HarnessEvent.from_mapping({
                "v": 1,
                "op": "set",
                "harness": "codex",
                "session_id": "abc",
                "state": state,
                "label": "project",
            })
            self.assertEqual(
                buddy_harness.alert_line(event),
                f"ALERT {buddy_harness.relay_id('codex', 'abc')} "
                f"{1 if state == 'approval' else 0}",
            )
            self.assertNotIn(" ALERT ", buddy_harness.relay_line(event))

    def test_test_sessions_remain_visibly_marked(self):
        self.assertTrue(buddy_harness.relay_id("sample", "#demo").startswith("#"))

    def test_harness_prefix_is_derived_not_registered(self):
        self.assertEqual(buddy_harness.harness_prefix("claude"), "CL")
        self.assertEqual(buddy_harness.harness_prefix("codex"), "CO")
        self.assertEqual(buddy_harness.harness_prefix("x"), "X")

    def test_watch_uses_same_private_relay_id(self):
        event = buddy_harness.HarnessEvent.from_mapping({
            "v": 1,
            "op": "set",
            "harness": "codex",
            "session_id": "thread-1",
            "state": "working",
            "label": "Project",
        })
        logical_id = buddy_harness.relay_id("codex", "thread-1")
        self.assertEqual(
            buddy_harness.watch_line(event, "/tmp/rollout.jsonl"),
            f"WATCH {logical_id} /tmp/rollout.jsonl codex Project",
        )
        self.assertEqual(buddy_harness.unwatch_line(event), f"UNWATCH {logical_id}")

    def test_json_contract(self):
        event = buddy_harness.parse_json_event(io.StringIO(
            '{"v":1,"op":"set","harness":"codex",'
            '"session_id":"x","state":"idle","label":"my repo"}'
        ))
        self.assertEqual(event.state, "idle")
        self.assertEqual(event.label, "my repo")

    def test_unknown_state_is_rejected(self):
        with self.assertRaises(buddy_harness.EventError):
            buddy_harness.HarnessEvent.from_mapping({
                "v": 1,
                "op": "set",
                "harness": "codex",
                "session_id": "x",
                "state": "thinking-ish",
                "label": "repo",
            })


if __name__ == "__main__":
    unittest.main()
