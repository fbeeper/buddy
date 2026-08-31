import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock


RELAY_PATH = os.path.expanduser("~/.local/share/buddy-display/buddy-relay.py")
RELAY_EXISTS = os.path.isfile(RELAY_PATH)
if RELAY_EXISTS:
    SPEC = importlib.util.spec_from_file_location("buddy_relay", RELAY_PATH)
    buddy_relay = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(buddy_relay)
else:
    buddy_relay = None


class FakeLink:
    def __init__(self):
        self.lines = []

    def send(self, line):
        self.lines.append(line)


@unittest.skipUnless(RELAY_EXISTS, "deployed buddy relay is not installed")
class SerialLinkClockTests(unittest.TestCase):
    def test_clock_sync_uses_local_time_and_is_rate_limited(self):
        link = buddy_relay.SerialLink()
        link.fd = 9
        local = buddy_relay.time.struct_time(
            (2026, 8, 28, 17, 42, 9, 4, 240, 1)
        )
        with mock.patch.object(buddy_relay.time, "time", return_value=100.0), \
             mock.patch.object(buddy_relay.time, "localtime", return_value=local), \
             mock.patch.object(link, "send") as send:
            link.sync_clock()
            link.sync_clock()

        send.assert_called_once_with("CLOCK 17 42 9")
        self.assertEqual(link.last_clock_sync, 100.0)

    def test_clock_override_sends_rate_limited_ping(self):
        link = buddy_relay.SerialLink()
        link.fd = 9
        link.clock_override_until = 200.0
        with mock.patch.object(buddy_relay.time, "time", return_value=100.0), \
             mock.patch.object(link, "send") as send:
            link.sync_clock()
            link.sync_clock()

        send.assert_called_once_with("PING")
        self.assertEqual(link.last_clock_sync, 100.0)


@unittest.skipUnless(RELAY_EXISTS, "deployed buddy relay is not installed")
class RowManagerTests(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.rows = buddy_relay.RowManager(self.link, state_path=None)
        self.now = 1000.0
        self.time_patcher = mock.patch.object(
            buddy_relay.time, "time", side_effect=lambda: self.now
        )
        self.time_patcher.start()

    def tearDown(self):
        self.time_patcher.stop()

    def add(self, session_id, color, text):
        self.rows.set(session_id, color, text)
        self.now += 1

    def test_end_middle_shifts_later_rows_and_clears_tail(self):
        self.add("a", "111111", "A")
        self.add("b", "222222", "B")
        self.add("c", "333333", "C")
        self.link.lines.clear()

        self.rows.end("b")

        self.assertEqual(self.rows.sessions["a"]["row"], 0)
        self.assertEqual(self.rows.sessions["c"]["row"], 1)
        self.assertEqual(self.rows.free_rows, [2, 3, 4, 5])
        self.assertEqual(
            self.link.lines,
            ["ROW 1 333333 C", "ROW 2 000000 "],
        )

    def test_end_first_preserves_order(self):
        self.add("a", "111111", "A")
        self.add("b", "222222", "B")
        self.add("c", "333333", "C")
        self.link.lines.clear()

        self.rows.end("a")

        self.assertEqual(self.rows.sessions["b"]["row"], 0)
        self.assertEqual(self.rows.sessions["c"]["row"], 1)
        self.assertEqual(
            self.link.lines,
            ["ROW 0 222222 B", "ROW 1 333333 C", "ROW 2 000000 "],
        )

    def test_end_last_only_clears_last_row(self):
        self.add("a", "111111", "A")
        self.add("b", "222222", "B")
        self.link.lines.clear()

        self.rows.end("b")

        self.assertEqual(self.link.lines, ["ROW 1 000000 "])
        self.assertEqual(self.rows.free_rows, [1, 2, 3, 4, 5])

    def test_end_unknown_id_does_nothing(self):
        self.add("a", "111111", "A")
        self.link.lines.clear()

        self.rows.end("missing")

        self.assertEqual(self.link.lines, [])
        self.assertEqual(self.rows.sessions["a"]["row"], 0)

    def test_expiry_compacts_survivors_and_next_allocation_follows_them(self):
        self.add("#stale-a", "111111", "A")
        self.add("keep-b", "222222", "B")
        self.add("#stale-c", "333333", "C")
        self.add("keep-d", "444444", "D")
        self.now += buddy_relay.SYNTHETIC_STALE_S + 1

        self.rows.expire_stale()
        self.add("new-e", "555555", "E")

        self.assertEqual(
            {sid: entry["row"] for sid, entry in self.rows.sessions.items()},
            {"keep-b": 0, "keep-d": 1, "new-e": 2},
        )
        self.link.lines.clear()
        self.rows.replay()
        self.assertEqual(
            self.link.lines,
            ["ROW 0 222222 B", "ROW 1 444444 D", "ROW 2 555555 E", "ALERT 0"],
        )

    def test_real_sessions_do_not_expire_due_to_silence(self):
        self.add("real-session", "111111", "idle")
        self.now += buddy_relay.SYNTHETIC_STALE_S * 100

        self.rows.expire_stale()

        self.assertIn("real-session", self.rows.sessions)

    def test_persisted_rows_survive_relay_restart_and_replay(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        state_path = os.path.join(directory.name, "relay-state.json")
        first_link = FakeLink()
        first = buddy_relay.RowManager(first_link, state_path=state_path)
        first.set("codex-abc", "3FAEDA", "project: idle")
        first.set("claude-def", "4CAF50", "other: working")

        second_link = FakeLink()
        restored = buddy_relay.RowManager(second_link, state_path=state_path)
        restored.replay()

        self.assertEqual(
            second_link.lines,
            ["ROW 0 3FAEDA project: idle", "ROW 1 4CAF50 other: working",
             "ALERT 0"],
        )
        with open(state_path, encoding="utf-8") as state_file:
            state = json.load(state_file)
        self.assertEqual(state["v"], 1)
        self.assertEqual([entry["id"] for entry in state["sessions"]],
                         ["codex-abc", "claude-def"])

    def test_alert_is_aggregated_across_sessions(self):
        self.add("a", "D4301B", "A")
        self.add("b", "D4301B", "B")
        self.rows.set_alert("a", True)
        self.rows.set_alert("b", True)
        self.link.lines.clear()

        self.rows.set_alert("a", False)
        self.rows.end("b")

        self.assertEqual(self.link.lines[-2:], ["ROW 1 000000 ", "ALERT 0"])

    def test_replay_restores_alert(self):
        self.add("approval", "D4301B", "A")
        self.rows.set_alert("approval", True)
        self.link.lines.clear()

        self.rows.replay()

        self.assertEqual(self.link.lines, ["ROW 0 D4301B A", "ALERT 1"])

    def test_clock_style_is_persisted_and_replayed_before_rows(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        state_path = os.path.join(directory.name, "relay-state.json")
        first_link = FakeLink()
        first = buddy_relay.RowManager(first_link, state_path=state_path)
        first.set("codex-abc", "3FAEDA", "project: idle")
        first.set_clock_style("dots")
        self.assertEqual(first_link.lines[-1], "CSTYLE dots")

        second_link = FakeLink()
        restored = buddy_relay.RowManager(second_link, state_path=state_path)
        restored.replay()

        self.assertEqual(restored.clock_style, "dots")
        self.assertEqual(
            second_link.lines,
            ["CSTYLE dots", "ROW 0 3FAEDA project: idle", "ALERT 0"],
        )

    def test_dotted_arcs_style_is_accepted(self):
        self.rows.set_clock_style("dotted-arcs")
        self.assertEqual(self.rows.clock_style, "dotted-arcs")
        self.assertEqual(self.link.lines, ["CSTYLE dotted-arcs"])



if __name__ == "__main__":
    unittest.main()
