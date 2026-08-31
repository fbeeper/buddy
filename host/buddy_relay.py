#!/usr/bin/env python3
"""Persistent relay daemon for the USB "buddy" status display.

Hook invocations (buddy-display.py) are fire-and-forget and must never block
a real Claude Code session, but opening this specific serial port from a
fresh process has been observed to take anywhere from instant to 30+ seconds
on this Mac. Paying that cost on every single hook event means status
updates (e.g. "waiting for approval") can arrive long after the moment
they're meant to reflect.

This daemon opens the serial port once and keeps it open, and listens on a
local Unix domain socket for lines to relay. Hook invocations become a fast
local socket write instead of a fresh serial open() -- once this daemon has
a connection established, forwarding a line is near-instant.

Run as a launchd LaunchAgent (see com.buddy.relay.plist) so exactly one
instance is always running. Binding the Unix socket doubles as a single-
instance lock: if another instance is already bound, this one exits quietly.

The device itself keeps no session policy: it is a dumb fixed-row terminal
(see BuddyProtocol.h) that understands

    ROW <index> <rrggbb> <text...>
    CLOCK <hour> <minute> <second>
    PING
    CSTYLE <arcs|dots|dotted-arcs>

The relay periodically sends host-local CLOCK anchors; the firmware advances
them with its monotonic timer to animate the decorative perimeter between
syncs.

This daemon is what turns an arbitrary logical id (a Claude Code session id
today; could be "weather" or anything else tomorrow) into a row index, and
owns all the policy the firmware used to: which id occupies which row,
eviction when the row pool is full, and clearing a row when its id has gone
stale. See RowManager. Callers (buddy-display.py, or any other producer)
speak a higher-level, id-based protocol over the local socket:

    SESSION <id> <rrggbb> <text...>   -- create/update the row for <id>
    ALERT <id> <0|1>                  -- set this id's attention flag
    END <id>                          -- free <id>'s row
    WATCH <id> <transcript_path> <profile> <label...>
    UNWATCH <id>
    CLOCK <hour> <minute> <second> [duration_s]
                                       -- fake the decorative clock for
                                          duration_s seconds (default 120),
                                          then resume real host time
    CSTYLE <arcs|dots|dotted-arcs>      -- select and durably persist the
                                          clock visualization

The label travels with WATCH (not just the id/path) because a SESSION line
by the time it reaches here only carries pre-formatted display text, not
the raw label -- if a transcript watch needs to resolve a stuck state back
to "idle" on its own, it needs the raw label to format that line correctly
via buddy_style, the same module buddy-display.py uses.

Some harness terminal outcomes do not fire lifecycle hooks. A profiled WATCH
follows only newly appended, complete JSONL records and delegates their
interpretation to buddy_transcript.py. Keeping harness-specific parsing out of
this relay preserves its primary role as generic row/serial infrastructure.

The device also starts every boot with all rows blank and has no way to ask
for current state -- it's a purely passive receiver. RowManager persists each
real id's row assignment/color/text and restores that table after daemon or Mac
restart. SerialLink.on_connect replays it whenever a fresh serial connection is
established, so a reboot or USB replug does not leave the display blank while
real sessions are still active. Only marked #synthetic rows expire due to
silence; real lifecycle is owned by SESSION/END.
"""
import glob
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buddy_style
import buddy_transcript

SOCKET_PATH = os.path.expanduser("~/.local/share/buddy-display/buddy-relay.sock")
STATE_PATH = os.path.expanduser("~/.local/share/buddy-display/buddy-relay-state.json")
RECONNECT_BACKOFF_S = 2.0
WATCH_POLL_INTERVAL_S = 0.5
BUDDY_MAX_ROWS = 6  # must match BuddyProtocol.h's BUDDY_MAX_ROWS
SYNTHETIC_STALE_S = 30 * 60  # only marked #test rows expire due to silence
CLOCK_SYNC_INTERVAL_S = 10.0

# A device that re-enumerates can keep the exact same /dev path (observed:
# bus address changed on a real physical unplug/replug, but the path string
# didn't), and writes to the old, now-orphaned fd can succeed silently on
# macOS instead of erroring -- so neither write-failure detection nor path-
# string comparison reliably catches this. A blind periodic full reconnect
# is the only thing that's proven reliable: worst case it's a wasted
# close+reopen, but it guarantees the fd can't stay silently stale forever.
FORCE_RECONNECT_INTERVAL_S = 15.0


def find_port():
    matches = sorted(glob.glob("/dev/cu.usbmodem*"))
    return matches[0] if matches else None


def log(msg):
    print(f"[buddy-relay] {msg}", flush=True)


class SerialLink:
    """Holds a possibly-open fd to the display, reconnecting lazily on use.

    on_connect (set after construction, once a RowManager exists) fires
    every time a fresh connection is established -- which only happens after
    the device rebooted or was replugged, since the device starts every boot
    with all rows blank and has no way to ask for current state. This is the
    hook point for replaying what the relay remembers.
    """

    def __init__(self):
        self.fd = None
        self.current_port = None
        self.last_attempt = 0.0
        self.last_open_time = 0.0
        self.last_clock_sync = 0.0
        self.clock_override_until = 0.0
        self.on_connect = None

    def _try_open(self):
        now = time.time()
        if now - self.last_attempt < RECONNECT_BACKOFF_S:
            return
        self.last_attempt = now
        port = find_port()
        if not port:
            return
        try:
            self.fd = os.open(port, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
            self.current_port = port
            self.last_open_time = now
            log(f"connected to {port}")
            if self.on_connect:
                self.on_connect()
        except OSError as e:
            log(f"open failed: {e}")
            self.fd = None
            self.current_port = None

    def force_periodic_reconnect(self):
        """Unconditional close+reopen every FORCE_RECONNECT_INTERVAL_S,
        regardless of whether anything appeared to fail -- the only
        reliable defense against a silently-orphaned fd on this Mac (see
        FORCE_RECONNECT_INTERVAL_S comment). Reopening onto the same live
        port is cheap; SESSION lines are idempotent, so a resulting replay
        of already-correct state is harmless even if redundant."""
        if self.fd is None:
            return
        if time.time() - self.last_open_time < FORCE_RECONNECT_INTERVAL_S:
            return
        log("periodic refresh reconnect")
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None
        self.current_port = None
        self.last_attempt = 0.0
        self._try_open()

    def check_port_changed(self):
        """A device that re-enumerates under a new /dev path (observed: this
        happens on some reboots) leaves the old fd silently "succeeding" on
        writes without ever reaching the new device -- macOS doesn't error
        the write, so failure detection in send() alone isn't reliable here.
        Called periodically to proactively reconnect when a better port
        shows up, independent of whether the current fd ever errors."""
        if self.fd is None:
            return
        port = find_port()
        if port and port != self.current_port:
            log(f"port changed ({self.current_port} -> {port}), reconnecting")
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
            self.current_port = None
            self.last_attempt = 0.0  # bypass backoff for this deliberate reconnect
            self._try_open()

    def send(self, line: str):
        if self.fd is None:
            self._try_open()
        if self.fd is None:
            log(f"dropped (no connection): {line!r}")
            return
        try:
            os.write(self.fd, (line + "\n").encode())
            log(f"sent: {line!r}")
        except OSError as e:
            log(f"write failed ({e}), will reconnect")
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
            self.current_port = None

    def sync_clock(self, force=False):
        """Send a clock anchor or heartbeat to the firmware every ten seconds.

        During a manual clock override, PING keeps relay liveness observable
        without clobbering the temporary clock value."""
        now = time.time()
        if not force and now - self.last_clock_sync < CLOCK_SYNC_INTERVAL_S:
            return
        if self.fd is None:
            self._try_open()
            return  # on_connect performs the initial forced sync
        if now < self.clock_override_until:
            self.send("PING")
        else:
            local = time.localtime(now)
            self.send(f"CLOCK {local.tm_hour} {local.tm_min} {local.tm_sec}")
        if self.fd is not None:
            self.last_clock_sync = now

    def set_clock_override(self, hour, minute, second, duration_s):
        """Fake the device's clock immediately; sync_clock() leaves it alone
        until duration_s elapses, then resumes real time on its own -- so a
        forgotten override can't strand the display on a fake time."""
        self.clock_override_until = time.time() + duration_s
        self.send(f"CLOCK {hour} {minute} {second}")


class RowManager:
    """Owns the mapping from an arbitrary logical id to one of the device's
    BUDDY_MAX_ROWS row slots, plus every bit of policy the firmware used to
    handle itself: allocation, eviction when the pool is full, durable state,
    synthetic-test expiry, and replay after a reconnect. The device has no idea
    any of this exists -- it just receives ROW <index> <color> <text> lines.

    Because allocation is keyed on an arbitrary string id with no built-in
    meaning, any producer can share the row pool: a Claude Code session id
    today, "weather" or anything else tomorrow, all going through the same
    SESSION/END commands on the local socket.
    """

    def __init__(self, link: SerialLink, state_path=STATE_PATH):
        self.link = link
        self.state_path = state_path
        self.free_rows = list(range(BUDDY_MAX_ROWS))
        self.sessions = {}  # id -> row/color/text/alert/timestamp
        self.clock_style = None  # None means use the firmware's hardcoded default
        self._load()

    def _load(self):
        """Restore the harness-neutral row table after daemon/Mac restart."""
        if not self.state_path:
            return
        try:
            with open(self.state_path, encoding="utf-8") as state_file:
                state = json.load(state_file)
        except (OSError, ValueError):
            return
        if not isinstance(state, dict) or state.get("v") != 1:
            return
        clock_style = state.get("clock_style")
        if clock_style in ("arcs", "dots", "dotted-arcs"):
            self.clock_style = clock_style
        entries = state.get("sessions")
        if not isinstance(entries, list):
            return

        restored = {}
        used_rows = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("id")
            row = entry.get("row")
            color = entry.get("color")
            text = entry.get("text")
            timestamp = entry.get("ts")
            alert = entry.get("alert", False)
            if not isinstance(session_id, str) or not session_id:
                continue
            if not isinstance(row, int) or row < 0 or row >= BUDDY_MAX_ROWS:
                continue
            if row in used_rows or not isinstance(color, str) or not isinstance(text, str):
                continue
            if not isinstance(timestamp, (int, float)):
                continue
            if not isinstance(alert, bool):
                continue
            restored[session_id] = {
                "row": row,
                "color": color,
                "text": text,
                "alert": alert,
                "ts": float(timestamp),
            }
            used_rows.add(row)

        self.sessions = restored
        self.free_rows = [row for row in range(BUDDY_MAX_ROWS) if row not in used_rows]
        if restored:
            log(f"restored {len(restored)} persisted session row(s)")

    def _save(self):
        """Atomically persist row ownership without storing raw harness ids."""
        if not self.state_path:
            return
        state = {
            "v": 1,
            "clock_style": self.clock_style,
            "sessions": [
                {"id": session_id, **entry}
                for session_id, entry in sorted(
                    self.sessions.items(), key=lambda item: item[1]["row"]
                )
            ],
        }
        temporary_path = self.state_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file, separators=(",", ":"))
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.state_path)
        except OSError as error:
            log(f"state save failed: {error}")
            try:
                os.unlink(temporary_path)
            except OSError:
                pass

    def _alloc_row(self, session_id: str) -> int:
        if self.free_rows:
            return self.free_rows.pop(0)
        # Pool full and this is an id we haven't seen: evict the
        # longest-idle entry rather than silently drop the new one.
        oldest_id = min(self.sessions, key=lambda sid: self.sessions[sid]["ts"])
        row = self.sessions.pop(oldest_id)["row"]
        log(f"row pool full, evicting {oldest_id} to make room for {session_id}")
        return row

    def set(self, session_id: str, color: str, text: str):
        was_alerting = self.is_alerting()
        entry = self.sessions.get(session_id)
        if entry is None:
            row = self._alloc_row(session_id)
            entry = {
                "row": row,
                "color": color,
                "text": text,
                "alert": False,
                "ts": time.time(),
            }
            self.sessions[session_id] = entry
        else:
            entry["color"] = color
            entry["text"] = text
            entry["ts"] = time.time()
        self._save()
        self.link.send(f"ROW {entry['row']} {color} {text}")
        if was_alerting != self.is_alerting():
            self._send_alert()

    def is_alerting(self):
        return any(entry["alert"] for entry in self.sessions.values())

    def _send_alert(self):
        self.link.send(f"ALERT {1 if self.is_alerting() else 0}")

    def set_alert(self, session_id: str, enabled: bool):
        entry = self.sessions.get(session_id)
        if entry is None or entry["alert"] == enabled:
            return
        entry["alert"] = enabled
        self._save()
        self._send_alert()

    def end(self, session_id: str):
        was_alerting = self.is_alerting()
        entry = self.sessions.pop(session_id, None)
        if entry is None:
            return

        # Keep the visible list contiguous while preserving its current
        # top-to-bottom order. Entries below the removed one move up by one;
        # entries above it retain their row. The old final row is then the
        # only slot that needs clearing.
        vacated_row = entry["row"]
        for remaining in sorted(self.sessions.values(), key=lambda e: e["row"]):
            if remaining["row"] <= vacated_row:
                continue
            remaining["row"] -= 1
            self.link.send(
                f"ROW {remaining['row']} {remaining['color']} {remaining['text']}"
            )

        last_active_row = len(self.sessions)
        self.link.send(f"ROW {last_active_row} 000000 ")
        self.free_rows = list(range(last_active_row, BUDDY_MAX_ROWS))
        self._save()
        if was_alerting != self.is_alerting():
            self._send_alert()

    def expire_stale(self):
        now = time.time()
        for session_id in [sid for sid, e in self.sessions.items()
                            if sid.startswith("#") and
                            now - e["ts"] > SYNTHETIC_STALE_S]:
            log(f"expiring stale synthetic session {session_id}")
            self.end(session_id)

    def set_clock_style(self, style: str):
        if style not in ("arcs", "dots", "dotted-arcs"):
            return
        self.clock_style = style
        self._save()
        self.link.send(f"CSTYLE {style}")

    def replay(self):
        if self.clock_style is not None:
            self.link.send(f"CSTYLE {self.clock_style}")
        for entry in self.sessions.values():
            self.link.send(f"ROW {entry['row']} {entry['color']} {entry['text']}")
        self._send_alert()
        log(f"replayed {len(self.sessions)} known session row(s) after reconnect")


class TranscriptWatcher:
    """Follow active transcript files for harness-specific terminal records.

    Parsing lives in buddy_transcript rather than this generic serial/row
    relay. A watch lasts for the row's real session lifetime; long thinking or
    tool calls are valid and must not silently disable recovery.
    """

    def __init__(self, rows: RowManager):
        self.rows = rows
        self.watches = {}  # id -> path/position/profile/label/pending bytes

    def watch(self, session_id: str, path: str, profile: str, label: str):
        existing = self.watches.get(session_id)
        if existing is not None and existing["path"] == path:
            # Re-arming an already-watched session (happens on every
            # PreToolUse/PostToolUse/UserPromptSubmit): refresh the profile
            # and label, but deliberately leave "pos" untouched. Resetting
            # it to the current file size here would
            # silently skip over a marker that arrived in the gap between
            # the last poll and this re-arm -- e.g. interrupt, then
            # immediately send the next message, whose UserPromptSubmit
            # would otherwise re-arm right past the marker before it was
            # ever scanned.
            existing["profile"] = profile
            existing["label"] = label
            return
        try:
            pos = os.path.getsize(path)
        except OSError:
            pos = 0
        self.watches[session_id] = {
            "path": path,
            "pos": pos,
            "profile": profile,
            "label": label,
            "pending": b"",
        }
        log(f"watching {session_id} ({path})")

    def unwatch(self, session_id: str):
        if self.watches.pop(session_id, None) is not None:
            log(f"unwatched {session_id}")

    def poll(self):
        resolved = []
        for session_id, w in self.watches.items():
            # END/expiry owns row lifetime. Keeping an orphaned file watch has
            # no value, but an active turn may legitimately run for hours.
            if session_id not in self.rows.sessions:
                resolved.append(session_id)
                continue
            try:
                with open(w["path"], "rb") as f:
                    f.seek(w["pos"])
                    new_data = f.read()
                    w["pos"] = f.tell()
            except OSError:
                continue
            if not new_data:
                continue
            chunks = (w["pending"] + new_data).split(b"\n")
            w["pending"] = chunks.pop()
            terminal_state = next((
                state for line in chunks if line
                if (state := buddy_transcript.resolution_for_line(w["profile"], line))
            ), None)
            if terminal_state is not None:
                log(f"transcript resolved {session_id} to {terminal_state}")
                color, text = buddy_style.format_session(terminal_state, w["label"], w["profile"])
                self.rows.set(session_id, color, text)
                self.rows.set_alert(session_id, False)
                resolved.append(session_id)
            # else: ordinary growth from legitimate ongoing work -- pos is
            # already advanced above, just keep watching.
        for session_id in resolved:
            self.watches.pop(session_id, None)


def handle_line(line: str, watcher: TranscriptWatcher, rows: RowManager):
    parts = line.split(" ", 1)
    cmd = parts[0] if parts else ""

    if cmd == "WATCH":
        rest = parts[1] if len(parts) > 1 else ""
        fields = rest.split(" ", 3)
        if len(fields) == 4 and fields[2] in ("claude", "codex", "auto"):
            session_id, path, profile, label = fields
        elif len(fields) >= 3:
            # Backward compatibility for the retired adapter and hand tests.
            session_id, path = fields[:2]
            profile = "auto"
            label = " ".join(fields[2:])
        elif len(fields) == 2:
            session_id, path = fields
            profile = "auto"
            label = session_id
        else:
            return
        watcher.watch(session_id, path, profile, label)
        return

    if cmd == "UNWATCH":
        rest = parts[1] if len(parts) > 1 else ""
        session_id = rest.strip()
        if session_id:
            watcher.unwatch(session_id)
        return

    if cmd == "SESSION":
        rest = parts[1] if len(parts) > 1 else ""
        fields = rest.split(" ", 2)
        if len(fields) == 3:
            session_id, color, text = fields
            rows.set(session_id, color, text)
        return

    if cmd == "ALERT":
        rest = parts[1] if len(parts) > 1 else ""
        fields = rest.split(" ", 1)
        if len(fields) == 2 and fields[1] in ("0", "1"):
            rows.set_alert(fields[0], fields[1] == "1")
        return

    if cmd == "CLOCK":
        rest = parts[1] if len(parts) > 1 else ""
        fields = rest.split()
        if len(fields) not in (3, 4):
            return
        try:
            hour, minute, second = (int(fields[0]), int(fields[1]), int(fields[2]))
            duration_s = float(fields[3]) if len(fields) == 4 else 120.0
        except ValueError:
            return
        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59 and duration_s > 0:
            rows.link.set_clock_override(hour, minute, second, duration_s)
        return

    if cmd == "CSTYLE":
        rest = parts[1] if len(parts) > 1 else ""
        style = rest.strip()
        if style in ("arcs", "dots", "dotted-arcs"):
            rows.set_clock_style(style)
        return

    if cmd == "END":
        rest = parts[1] if len(parts) > 1 else ""
        session_id = rest.strip()
        if session_id:
            rows.end(session_id)
        return


def main():
    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(SOCKET_PATH)
    except OSError as e:
        log(f"bind failed ({e}) -- another instance is likely already running, exiting")
        sys.exit(0)
    srv.listen(8)
    srv.settimeout(WATCH_POLL_INTERVAL_S)
    log(f"listening on {SOCKET_PATH}")

    link = SerialLink()
    rows = RowManager(link)
    watcher = TranscriptWatcher(rows)
    def replay_display():
        rows.replay()
        link.sync_clock(force=True)

    link.on_connect = replay_display
    link.sync_clock()

    while True:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            link.check_port_changed()
            link.force_periodic_reconnect()
            watcher.poll()
            rows.expire_stale()
            link.sync_clock()
            continue

        try:
            conn.settimeout(1.0)
            data = b""
            try:
                while True:
                    chunk = conn.recv(256)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
            except socket.timeout:
                pass
            line = data.decode(errors="replace").strip()
            if line:
                handle_line(line, watcher, rows)
            else:
                log("connection with no data")
        finally:
            conn.close()

        link.check_port_changed()
        link.force_periodic_reconnect()
        watcher.poll()
        rows.expire_stale()
        link.sync_clock()


if __name__ == "__main__":
    main()
