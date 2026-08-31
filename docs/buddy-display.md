# Buddy display: setup, samples, and harness integration

This guide is for people who want to put a status row on the round display,
or connect a coding harness such as Claude Code or Codex to it.

## The short version

Do not open the USB serial port from a hook or sample. The persistent relay is
the only process that owns that port. Producers send short messages to its
Unix socket instead:

```text
coding harness -> host/buddy_harness.py -> buddy-relay.py -> USB serial -> firmware
 native events       standard states        row owner       ROW lines     pixels
```

On the development Mac, check that the relay is running and run the safe demo:

```bash
pgrep -fl buddy-relay.py
python3 host/buddy_harness.py demo
```

The demo uses a visibly synthetic `#demo` session, cycles one row through the
available states, and removes the row in a `finally` block. Tilt the board
upright if the status tile is not visible.

Watch what the relay actually sends to the device:

```bash
tail -f ~/.local/share/buddy-display/logs/buddy-relay.log
```

## Command-line clients

Two clients share `host/buddy_transport.py`, which performs one short Unix-
socket write and never opens USB serial:

- `host/buddy_harness.py` is for per-session coding-harness lifecycle.
- `host/buddy_config.py` is for device-wide configuration and visual previews.

Both accept the same global options, placed **before** the subcommand:

```text
--socket PATH       override the relay socket (normally unnecessary)
--timeout SECONDS   socket timeout; default 0.3
--best-effort       return success when the relay is unavailable
```

Use `--best-effort` in production hooks so a decorative display cannot break a
coding session. Omit it during manual diagnosis so connection errors are
visible. Discover the current syntax with:

```bash
python3 host/buddy_harness.py --help
python3 host/buddy_harness.py set --help
python3 host/buddy_config.py --help
python3 host/buddy_config.py clock-style --help
```

### Safe lifecycle demo

```bash
python3 host/buddy_harness.py demo
python3 host/buddy_harness.py demo --delay 1.5
```

`demo` cycles a synthetic `#demo` row through representative states and sends
its matching `end` in a `finally` block.

### Choose the clock visualization

The status tile has three mutually exclusive clock styles:

- `arcs`: clean hour and minute progress arcs, plus the moving seconds dot.
- `dots`: 12 hour dots and 60 minute dots, all the same diameter as the
  seconds dot. The current hour and minute dots use the full ring color while
  the remaining dots use its darker shade.
- `dotted-arcs`: the dim hour/minute dot rings form a background clock face;
  clean progress arcs are drawn above them. There are no highlighted hour or
  minute dots because the arcs indicate progress. The seconds dot remains in
  the foreground.

Select one through the device-configuration client; neither this command nor any
harness adapter opens the serial port:

```bash
python3 host/buddy_config.py clock-style arcs
python3 host/buddy_config.py clock-style dots
python3 host/buddy_config.py clock-style dotted-arcs
```

The relay writes the selection to `buddy-relay-state.json` and sends it to the
device immediately. It is restored after relay/Mac restart and replayed after
device reboot or USB reconnect. If no host selection has ever been persisted,
the firmware uses `BUDDY_CLOCK_STYLE_DEFAULT` from `BuddyData.h`, currently
`dotted-arcs`.

### Preview a specific time

`clock` changes the displayed time temporarily and is independent of the
selected visualization:

```bash
python3 host/buddy_config.py clock 10 9 30 --duration 120
```

Arguments are `hour minute second`; hour is 0–23 and minute/second are 0–59.
The relay automatically resumes real host-local time after `--duration`
seconds (default 120), so a forgotten preview cannot permanently freeze time.

### Create, update, and remove a row

Use a stable harness name and a stable session id. The session id is hashed
before it reaches the relay logs; the label is the short human-readable name
shown on screen.

```bash
python3 host/buddy_harness.py set my-tool session-42 working firmware
python3 host/buddy_harness.py set my-tool session-42 approval firmware
python3 host/buddy_harness.py set my-tool session-42 idle firmware
python3 host/buddy_harness.py end my-tool session-42
```

Always send `end` for manual tests. Prefix a test session id and label with
`#`, so accidental leftovers are recognizable:

```bash
python3 host/buddy_harness.py set sample '#test01' working '#test'
python3 host/buddy_harness.py end sample '#test01'
```

The `set` syntax is:

```text
buddy_harness.py set HARNESS SESSION_ID STATE LABEL
```

`STATE` is one of `idle`, `working`, `waiting`, `approval`, `compacting`, or
`error`. Reusing the same `HARNESS` and `SESSION_ID` updates the same row;
`end HARNESS SESSION_ID` removes it. Quote values containing spaces, and quote
`#`-prefixed test values because an unquoted `#` begins a shell comment.

### Send the versioned JSON contract

`json` reads exactly one version-1 lifecycle event from standard input. This
is the recommended boundary for a real adapter that already has a structured
native payload. Harness adapters should use this JSON contract rather than choosing colors,
formatting display text, assigning rows, or touching serial ports themselves.
Send exactly one JSON object on standard input:

```bash
printf '%s\n' '{"v":1,"op":"set","harness":"codex","session_id":"thr_123","state":"working","label":"firmware"}' \
  | python3 host/buddy_harness.py --best-effort json
```

`--best-effort` is recommended in real hooks: an unplugged decorative display
must not delay or break a coding session.

### `set`

```json
{
  "v": 1,
  "op": "set",
  "harness": "codex",
  "session_id": "thr_123",
  "state": "approval",
  "label": "firmware"
}
```

Fields:

- `v`: protocol version; currently `1`.
- `op`: `set` creates or updates a logical row.
- `harness`: stable producer name matching `[A-Za-z0-9_.-]{1,24}`.
- `session_id`: stable native conversation/session id. It may contain private
  or awkward characters because the middle layer hashes it before logging it.
- `state`: one of `idle`, `working`, `waiting`, `approval`, `compacting`, or
  `error`.
- `label`: user-facing conversation/project name. Newlines are removed and
  only the first six characters currently fit beside the state word.

`waiting` means the harness needs unspecified user input. Use `approval` when
the pending action is specifically a permission decision; it is clearer at a
glance on the small screen. Approval also asserts a generic attention flag that
pulses the backlight until every approving session has resolved.

### `end`

```json
{
  "v": 1,
  "op": "end",
  "harness": "codex",
  "session_id": "thr_123"
}
```

`end` frees the row immediately. It must use the same `harness` and native
`session_id` as preceding `set` events.

### Why this middle layer exists

The versioned event contract gives every harness the same narrow job: map its
native lifecycle events to canonical display states. Display policy stays in
one place. This prevents Claude and Codex integrations from drifting into
different colors, labels, cleanup rules, or unsafe serial behavior.

The current client translates version-1 events to the already-running relay's
line protocol. This is intentionally an evolutionary layer: the relay can
accept JSON natively later without changing harness adapters or their event
vocabulary.

## What a good coding-harness adapter must do

An adapter is a state machine. A turn-complete notification by itself is not
enough: the useful moment is often when the harness is blocked and needs the
human.

| Harness situation | Canonical event |
| --- | --- |
| Session created or resumed, no turn active | `set idle` |
| User submits a prompt | `set working` |
| Tool work begins or continues | `set working` |
| Permission prompt is shown | `set approval` |
| Other user input is required | `set waiting` |
| Context compaction (when both begin/end events exist) | `set compacting`, then `set working` |
| Turn stops normally | `set idle` |
| Unrecoverable harness/turn failure | `set error` |
| Session is really closed/deleted/expired | `end` |

The adapter also needs to satisfy these operational rules:

1. Use a stable native session id. A process id, current directory, or display
   label alone is not unique enough when several conversations run at once.
2. Resolve the display label on every event. Renames should appear without
   restarting a session. Never put raw prompts, tool arguments, secrets, or
   transcript content on the display.
3. Be fast and fail open. Connect only to the local socket, use a short timeout,
   swallow display failures in production hooks, and never wait for USB.
4. Preserve event order. Do not launch state-changing updates asynchronously
   unless the adapter serializes them; a late `working` update must not overwrite
   a newer `approval` or `idle` update.
5. Make updates idempotent. Lifecycle hooks may repeat after resume, reconnect,
   retry, or compaction.
6. Handle parallel sessions independently. Include the harness name in the
   logical identity so equal ids from two tools cannot collide. Decide whether
   subagents share their parent's row or intentionally receive separate rows.
7. Recover from missing events. Send explicit recovery events where the harness
   supports them. Transcript polling is a harness-specific fallback, not part
   of the standard API.
8. Clean up deliberately. Send `end` only when the session really ends, not when
   the user merely switches tabs. Real sessions do not expire merely because
   they are quiet; `end` is the authoritative portable lifecycle signal.

## What the shared relay owns

`buddy-relay.py` is the single serial-port owner. It currently runs as the
`com.buddy.relay` macOS LaunchAgent and listens at:

```text
~/.local/share/buddy-display/buddy-relay.sock
```

The relay and its socket are harness-neutral -- any producer can use it, not
just Claude Code. The relay:

- maps arbitrary logical ids onto rows 0 through 5;
- updates an existing id in place;
- evicts the least recently updated id if all six rows are occupied;
- persists real session rows across relay and Mac restarts;
- clears only `#`-prefixed synthetic/test rows after roughly 30 minutes;
- reconnects to `/dev/cu.usbmodem*`; and
- replays current rows after reconnect because the device boots blank.

Durable state lives at `~/.local/share/buddy-display/buddy-relay-state.json`. It contains
only the relay's already-private hashed ids and formatted display rows, not raw
harness session ids, prompts, tool arguments, or transcripts. Every `SESSION`
and `END` updates it atomically. On daemon start the relay restores that table;
on every serial reconnect it replays it. This behavior is harness-neutral:
Claude Code, Codex, and future adapters receive it automatically when they use
the standard `SESSION`/`END` contract.

The current reference deployment consists of:

```text
~/.local/share/buddy-display/buddy-relay.py
~/.local/share/buddy-display/buddy_style.py
~/.local/share/buddy-display/buddy_transcript.py
~/Library/LaunchAgents/com.buddy.relay.plist
```

The relay must be running before samples or harness adapters can update the
display. Editing only a per-invocation harness adapter needs no daemon restart;
editing relay or shared styling code does.

## Start, stop, and restart the relay daemon

Run these as the logged-in desktop user, not with `sudo`. The `gui/$(id -u)`
domain is that user's launchd session.

### Check status

```bash
pgrep -fl buddy-relay.py
launchctl print gui/$(id -u)/com.buddy.relay
tail -20 "$HOME/.local/share/buddy-display/logs/buddy-relay.log"
```

`pgrep` should show the Python process. `launchctl print` provides launchd's
loaded/running details. A healthy log normally contains `listening`,
`connected`, `replayed N known session row(s)`, and periodic `CLOCK` lines.

### Start an unloaded relay

```bash
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.buddy.relay.plist"
```

Use `bootstrap` when the service is currently unloaded, such as after an
explicit stop. Running it for an already-loaded service reports an error rather
than starting a second copy; the Unix socket also prevents duplicate relays.

### Stop the relay

```bash
launchctl bootout gui/$(id -u)/com.buddy.relay
```

Stopping releases the Unix socket and the exclusive USB-serial file descriptor.
This is mandatory before flashing followed by a raw-port smoke test. `bootout`
can report that the service was not found when it was already stopped.

### Restart after Python source changes

```bash
launchctl kickstart -k gui/$(id -u)/com.buddy.relay
```

`kickstart -k` replaces the running daemon process while leaving its LaunchAgent
loaded. Use it after changing the installed relay, style, or transcript parser.
It does not reload changes to the `.plist` itself.

### Reload after LaunchAgent plist changes

```bash
launchctl bootout gui/$(id -u)/com.buddy.relay
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.buddy.relay.plist"
```

After any start or restart, verify the result instead of assuming launchd
accepted it:

```bash
tail -20 "$HOME/.local/share/buddy-display/logs/buddy-relay.log"
```

A daemon restart does **not** erase rows or clock configuration. Durable state
is intentionally reloaded from `buddy-relay-state.json`, then replayed to the
device. Active harnesses can also immediately write fresh state after a reset.

The repository relay source is `host/buddy_relay.py`; the LaunchAgent executes
the installed copy. To deploy a source change:

```bash
python3 -m py_compile host/buddy_relay.py
./host/install_relay.sh
```

`install_relay.sh` copies `buddy_relay.py` and `buddy_transcript.py` to
`~/.local/share/buddy-display/`, rewrites the LaunchAgent plist, and restarts
it -- no manual `cp`/`kickstart` needed.

## Lower-level relay protocol

Most integrations should use the versioned harness API. For debugging, the
relay accepts one newline-terminated command per socket connection:

```text
SESSION <id> <rrggbb> <text...>
ALERT <id> <0|1>
END <id>
WATCH <id> <transcript_path> <profile> <label...>
UNWATCH <id>
CSTYLE <arcs|dots|dotted-arcs>
```

`SESSION` creates or updates a row without changing its wire format. `ALERT`
sets that id's attention flag; the relay aggregates all ids and sends the device
one `ALERT 0|1`, so resolving one approval cannot silence another. `END` frees
the row and shifts any later rows upward so the visible list stays contiguous.
`profile` is currently `claude`
or `codex`. `WATCH` follows only content appended after it is armed and asks
the isolated `buddy_transcript.py` parser whether a complete JSONL record is a
terminal lifecycle fallback. New harnesses should prefer native lifecycle
hooks and add a tested parser profile only for a demonstrated hook gap.
`CSTYLE` is global display configuration rather than session state. The relay
persists it and replays it before rows whenever serial reconnects.

Direct Python example:

```python
import os, socket

def send(line):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.3)
        client.connect(os.path.expanduser("~/.local/share/buddy-display/buddy-relay.sock"))
        client.sendall((line + "\n").encode())

send("SESSION #test01 4CAF50 #test: working")
send("END #test01")
```

## Firmware source architecture

Firmware responsibilities are deliberately split so feature work does not
accumulate again in `BuddyMain.c`:

| Module | Owns |
| --- | --- |
| `BuddyProtocol.c/.h` | USB CDC line buffering, parsing, and validation only |
| `BuddyData.c/.h` | In-memory rows, clock anchor/style, and attention flag |
| `BuddyClock.c/.h` | Clock widgets, all three visual styles, dot drawing, and time updates |
| `BuddyPictureTile.c/.h` | Construction of the boot image tile |
| `BuddyStatusTile.c/.h` | Status tile/panel/labels and attention backlight pulse |
| `BuddyMain.c/.h` | LVGL display/DMA setup, tile assembly, IMU switching, and rotation |
| `LCD_1in28_LVGL_test.c` | Main-loop orchestration and watchdog servicing |

The data flow is one-way: `BuddyProtocol` updates `BuddyData`; the clock and
status components read `BuddyData`; `BuddyMain` only creates the components
and owns navigation/display mechanics. Put new clock behavior in `BuddyClock`,
row presentation in `BuddyStatusTile`, and model fields in `BuddyData`. Do not
put feature-specific widgets or protocol policy back into `BuddyMain.c`.

`firmware/CMakeLists.txt` uses `aux_source_directory`, which discovers files at
CMake configure time. Ordinary edits need only `cmake --build build`, but after
adding or removing a `.c` file run `cmake -S . -B build` once before building.

## Firmware protocol

Only the relay should normally use the USB protocol:

```text
ROW <index 0-5> <rrggbb> <text...>
CLOCK <hour 0-23> <minute 0-59> <second 0-59>
PING
CSTYLE <arcs|dots|dotted-arcs>
ALERT <0|1>
```

The firmware keeps six rows, truncates display text to 24 characters, and
forgets every row on reboot. An empty text blanks a row. It has no sessions,
state names, expiry policy, or reconnect handshake. `CLOCK` is independent of
the row/session abstraction: the relay sends host-local wall time on connect
and every ten seconds, while the firmware uses its monotonic millisecond timer
to advance the clock between syncs. During a temporary clock override the
relay sends `PING` at the same interval instead, so it does not reset the fake
clock. The firmware treats valid relay traffic as a heartbeat and shows a
centered red `:(` below the session list after 15 seconds of silence; the face
disappears on the next valid command. `CSTYLE` switches among the clean arc,
discrete dot, and dotted-arc renderers in RAM. Persistence deliberately lives
in the relay: a device reboot first uses the compiled default and then adopts
the relay's saved style as soon as it reconnects. A device boot has no valid
wall-clock time until the relay supplies a fresh `CLOCK` anchor.

Never open the serial port while the relay is running. Opening this particular
device from two processes has hard-frozen the development Mac before. For a
firmware-only smoke test, stop the relay first and use one process that both
writes and reads the port, following [AGENTS.md](../AGENTS.md).

## Claude Code reference behavior

Claude Code's hooks invoke the installed copy of `host/claude_buddy_hook.py`
at `~/.claude/hooks/claude_buddy_hook.py` (see `host/install_claude_hooks.sh`
in [AGENTS.md](../AGENTS.md)), not the repo checkout directly, so the
repo can move or be deleted after installing. Like the Codex adapter, it
translates native events into
`HarnessEvent` objects and delegates styling, private ids, and lifecycle relay
command construction to `host/buddy_harness.py`; `host/buddy_transport.py`
owns the actual socket write. It retains only
Claude-specific name lookup, event mapping, and watch decisions. The former
machine-local `~/.claude/hooks/buddy-display.py` is no longer on the active
hook path.

The Claude integration demonstrates several details that belong in every
adapter:

- look up the actual user-facing session name, with prompt/cwd fallbacks;
- use `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, tool,
  compaction, `Stop`, and `SessionEnd` events rather than only completion;
- restore `working` after an approved tool actually begins;
- return to `idle` after normal stop; and
- use a transcript watcher only to compensate for Claude lifecycle gaps around
  interactive denial and Escape interruption.

Claude's watcher recognizes `toolDenialKind` and `interruptedMessageId` in new
JSONL content. Current Claude versions may instead append an exact synthetic
user message (`[Request interrupted by user]` or its `for tool use` variant),
so that form is recognized structurally as well. An assistant API-error record
with `error: "rate_limit"` or a rejected `quotaLimits` object resolves the turn
too; this covers quota/session limits that do not reliably fire `Stop` and
would otherwise leave `working` or `approval` stuck. Other API errors are not
assumed terminal because Claude may retry them automatically. These fields are
Claude implementation
details isolated in `host/buddy_transcript.py`; they do not enter the standard
harness event API or Codex's parser profile.

### Lifecycle recovery: how the fallback works

Native hooks are always the first source of truth. `UserPromptSubmit` puts the
row in `working`, `PermissionRequest` puts it in `approval`, tool hooks restore
`working`, and `Stop` restores `idle`. `SessionEnd` removes the row. The
adapter also sends a profiled `WATCH` while a turn is active because neither
Claude nor Codex reliably emits a native hook for every Escape cancellation.

The relay records the transcript's current byte position when a watch starts.
It reads only subsequently appended, newline-complete JSON records and routes
each record to the named parser profile. Parsing is structural: quoted marker
text inside a prompt, assistant explanation, or tool output is not considered
a lifecycle event. A recognized cancellation, denial, or terminal API failure
sets the row to `idle` and disarms the watch.

Re-arming after a tool event updates the display label but deliberately keeps
the previous byte position, preventing a fast cancel/new-prompt race from
skipping an unread terminal record. Watches have no short elapsed-time cutoff:
long thinking and long-running tools are valid. A watch ends on `Stop`,
`SessionEnd`, or a recognized terminal record. Real row lifetime is controlled
by `END`, not inactivity.

This mechanism is deliberately a fallback. Transcript formats are not public
contracts. Each recognized record shape therefore has a sanitized fixture in
`host/test_buddy_transcript.py`; when a harness changes its JSONL format, its
profile and fixtures should change together without touching firmware, row
allocation, or the other harness profile.

## Codex integration

Current Codex supports lifecycle hooks for `SessionStart`, `SessionEnd`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`,
`PreCompact`, `PostCompact`, and `Stop`. Hook commands receive JSON on standard
input containing a stable `session_id`, `cwd`, event name, and usually a
`turn_id`; this is enough to implement the mapping above.

The repository includes `host/codex_buddy_hook.py`, which maps these native
events onto the version-1 harness contract, and `host/codex-hooks.json`, the
user-wide hook definition installed as `~/.codex/hooks.json` on this Mac.
The adapter refreshes names from `~/.codex/session_index.jsonl` and keeps a
small per-session fallback under `~/.codex/buddy-labels/`; this prevents a new
conversation from changing back to its directory name before Codex has indexed
its generated title. `SessionEnd` removes that cached label.

Important Codex-specific details:

- Put user-wide hooks in `~/.codex/hooks.json`; project hooks require project
  trust. Review and trust new or changed definitions with `/hooks`.
- Codex fires `PermissionRequest` for every escalated action, including actions
  resolved by its automatic approval reviewer. The hook payload does not name
  the reviewer. The adapter therefore reads the matching `turn_context` from
  the supplied transcript: `auto_review` remains `working`, while `user`
  becomes the red `approval` state. If that context is absent or its schema
  changes, the adapter conservatively shows `approval` rather than hiding a
  real request for user input.
- Codex emits `PreCompact` before context compaction and `PostCompact` after it.
  The adapter maps those events to `compacting` and then back to `working` so
  the display shows the operation without remaining stuck afterward.
- Codex currently has no ESC/cancel hook. While a turn is active, the adapter
  arms the relay's transcript watcher. The relay recognizes Codex's structured
  `event_msg` / `turn_aborted` record and restores `idle`. The JSONL transcript
  is an implementation-detail fallback and should be kept narrow and tested
  when Codex changes.
- Codex calls the submitted text field `prompt`, whereas the current Claude
  adapter expects `user_input`; the adapters cannot be identical parsers.
- `Stop` hooks must emit valid JSON on stdout when exiting successfully. A
  status-only adapter should print `{}` after its best-effort socket update.
- `SessionEnd` may occur when a conversation is archived/deleted, Codex closes,
  or after it has been unopened and idle for 30 minutes. Switching away does
  not immediately mean end, so `Stop -> idle` and relay expiry remain important.
- Codex side chats identify themselves in the transcript's first
  `session_meta` record with an object-valued `source` containing `subagent`.
  They currently emit `Stop` when work completes but no `SessionEnd` when the
  side-chat panel closes. The adapter therefore treats subagent `Stop` as
  `end`: side work is visible while active and cannot leave an orphaned idle
  row. Ordinary `source: "cli"` conversations still use `Stop -> idle`.
- Hook commands are synchronous by default. That is useful for ordering, but
  the socket timeout must stay short. Background hooks can finish out of order
  and should not directly race state updates.
- Transcript paths are available for convenience, but Codex documents the
  transcript format as unstable. First validate native denial and interruption
  behavior; add a watcher only for a demonstrated missing event.
- The existing `notify` command in `~/.codex/config.toml` is completion-oriented
  and already serves another local integration. Lifecycle hooks can coexist
  without replacing it.

Official references: [Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Rebuild and flash the device

Run this from the project’s `C/` directory. Stop the relay first whenever the
test will open the raw serial port; two processes must never own this device's
port at the same time.

```bash
launchctl bootout gui/$(id -u)/com.buddy.relay
export PATH="$HOME/.pico-sdk/cmake/v4.3.4/bin:$HOME/.pico-sdk/ninja/v1.13.2:$PATH"
cmake --build build
"$HOME/.pico-sdk/picotool/2.3.0/picotool/picotool" \
  load -f -u -v -x build/RP2350-LCD-1.28.elf
```

The `-f` option asks running firmware to enter BOOTSEL, `-u` avoids disturbing
unwritten flash ranges, `-v` verifies the write, and `-x` reboots into the new
application. Success includes `Verifying Flash ... OK`. Use the physical
BOOTSEL button only when software reboot cannot find or reset the board.

After flashing, run the bounded firmware-only row/clock smoke test in the
“Repeatable build -> flash -> smoke-test recipe” in `AGENTS.md`. It deliberately
uses one process for both serial writes and reads and cleans up its `#flash`
row. Then always restore the daemon:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.buddy.relay.plist"
tail -20 "$HOME/.local/share/buddy-display/logs/buddy-relay.log"
```

The relay should reconnect and replay the saved clock style, current rows, and
`CLOCK`. Reflashing
the same already-built ELF is also a valid repeatability
test; omit `cmake --build build` only when that ELF is known to be current.

## Troubleshooting

- No row appears: tilt the board upright, check `pgrep -fl buddy-relay.py`, and
  inspect the relay log.
- Socket missing or refused: restart the LaunchAgent. Harness hooks using
  `--best-effort` intentionally hide this failure; rerun without it to diagnose.
- Device reconnects repeatedly: stop the relay before raw firmware testing so
  it cannot replay a crashing line forever.
- A row remains after a test: run the matching `end` command. If necessary, use
  the exact same harness and session id; row identity is derived from both.
- A row remains `working`/`approval` after Escape or a quota error: confirm the
  relay logged `watching <id>` followed by `transcript resolved <id> to idle`.
  If the first line is absent, inspect adapter hook delivery; if only the
  second is absent, capture the new sanitized terminal JSONL record and add a
  profile fixture before changing detection.
- Six real sessions are visible and another appears: the relay intentionally
  evicts the least recently updated row.
