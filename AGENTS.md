# AGENTS.md

Orientation for an agent picking up work in this repo. Read this before touching code.

## What this is

Firmware + host tooling for a Waveshare **RP2350-LCD-1.28-B**: a round 240x240
SPI LCD dev board (RP2350 / Pico 2, RISC-V "Hazard3" core) running LVGL. Two
things live on the round screen. Each boot starts on the image; holding the
board upright switches to the status display and latches there until reboot
(IMU-driven, deliberately no switch back while running). Display rotation
continues following the IMU in stable 90-degree steps so content remains
upright whichever edge the board rests on:

- **Tile 0**: a static image.
- **Tile 1**: the "buddy" status display — a live, per-row status readout
  driven over USB-serial by a host-side daemon. Originally built to show
  Claude Code session state ("working" / "waiting for approval" / etc.) but
  the device has no idea that's what it's showing (see below).

Not a git repository. There's no touch controller on this board — the "-B"
suffix is a case revision, not "RP2350-Touch-LCD-1.28-B". Don't try to wire
up touch code; it was removed on purpose.

The repository-level MIT license covers original project code only. Read
`THIRD_PARTY_NOTICES.md` before publishing or redistributing the source or a
firmware binary. The generated status font is a JetBrains Mono v2.304 ASCII
subset under SIL OFL 1.1, and the embedded dog photograph is Copyright (c)
2026 fbeeper under CC BY 4.0. Do not replace either with an unlicensed system
font or image. The Waveshare LCD and QMI8658 driver portions are Apache-2.0,
not MIT. Their exact official component paths, pinned provenance, and local
Apache license copy are recorded in `THIRD_PARTY_NOTICES.md`; preserve those
notices when modifying or redistributing the drivers.

## Layout

```
C/
  CMakeLists.txt                top-level build (target: RP2350-LCD-1.28)
  pico_sdk_import.cmake
  build/                        out-of-tree cmake+ninja build dir (already configured)
  uf2/RP2350-LCD-1.28.uf2       a prebuilt UF2 (stale after any source edit -- rebuild)
  firmware/
    CMakeLists.txt              production firmware library target
    include/ BuddyData.h BuddyProtocol.h BuddyClock.h BuddyPictureTile.h
             BuddyStatusTile.h BuddyUI.h BuddyMain.h LCD_test.h ImageData.h
    src/  BuddyData.c BuddyProtocol.c BuddyClock.c BuddyPictureTile.c
          BuddyStatusTile.c BuddyMain.c LCD_1in28_LVGL_test.c ImageData.c
          buddy_font_mono14.c main.c
  lib/
    Config/   DEV_Config.c/.h        low-level GPIO/SPI/PWM/delay wrappers
    LCD/      LCD_1in28.c/.h         panel driver
    QMI8658/  QMI8658.c/.h           IMU driver (orientation/tilt sensing)
    lvgl/     vendored LVGL v8.1.0
```

`firmware/src/BuddyData.c` + `.h` — firmware state model: rows, synchronized
clock anchor, selected clock style, and attention flag. It has no serial or
LVGL dependency.
`firmware/src/BuddyProtocol.c` + `.h` — USB-serial line parsing only; validated
commands update `BuddyData`.
`firmware/src/BuddyClock.c` + `.h` — all clock widgets, dot primitives, styles,
and time-driven updates.
`firmware/src/BuddyPictureTile.c` + `.h` — image tile construction.
`firmware/src/BuddyStatusTile.c` + `.h` — status tile/panel/row labels and
attention backlight pulse.
`firmware/src/BuddyMain.c` — LVGL display/DMA setup, tile orchestration, and
tilt/rotation behavior (`Widgets_PollOrientation`). Keep feature UI out of it.
`firmware/src/LCD_1in28_LVGL_test.c` — the main loop: LVGL tick, orientation
poll, protocol polling, component updates, and hardware watchdog.

The relay daemon is harness-neutral (it serves Claude Code, Codex, and any
future harness equally) and lives outside this repo at a fixed,
harness-independent location:

```
~/.local/share/buddy-display/
  buddy-relay.py       persistent daemon (LaunchAgent), owns the serial connection
  buddy_style.py       shared "what does each state look like" policy (source: host/)
  buddy_transcript.py  harness-specific JSONL fallback parser (source: host/)
  buddy_harness.py     harness-neutral event API -- both adapters import it (source: host/)
  buddy_transport.py   harness-neutral socket client -- both adapters import it (source: host/)
  buddy_config.py      device-wide config/preview CLI, repo-independent (source: host/)
  logs/buddy-relay.log / .err.log
  buddy-relay.sock      Unix domain socket the relay listens on
  buddy-relay-state.json  persisted row/session state
~/Library/LaunchAgents/com.buddy.relay.plist   LaunchAgent config for the relay
```

The versioned relay source is `host/buddy_relay.py`. Run `host/install_relay.sh`
to copy it, `buddy_style.py`, `buddy_transcript.py`, `buddy_harness.py`,
`buddy_transport.py`, and `buddy_config.py` there, write the LaunchAgent
plist, and (re)start it. Re-run the installer after editing any of those six
files.

`buddy_harness.py` and `buddy_config.py` are also usable as CLIs straight
from this installed location (`python3 ~/.local/share/buddy-display/buddy_harness.py ...`,
same for `buddy_config.py`) without the repo checked out -- this mirrors how
the docs' `python3 host/buddy_harness.py ...` / `host/buddy_config.py ...`
examples work when run from the repo; both locations work equally well since
each has its own `buddy_transport.py` sibling.

`buddy_harness.py` and `buddy_transport.py` live only in this one shared
location -- not copied into each harness's hooks dir -- because both hook
adapters import the identical files; each adapter inserts
`~/.local/share/buddy-display` onto `sys.path` before importing them. Each
harness's own hook adapter still lives under that harness's own config
directory, since only the adapter itself is harness-specific:

```
~/.claude/hooks/
  claude_buddy_hook.py active Claude adapter (source: host/claude_buddy_hook.py)
  buddy-display.py     legacy Claude adapter, no longer on the active hook path
```

The versioned Claude hook source is `host/claude_buddy_hook.py`. Run
`host/install_claude_hooks.sh` to copy it to `~/.claude/hooks/` and repoint
`~/.claude/settings.json`'s hook `command` entries at that fixed location --
this never bakes this repo's checkout path into your live settings, so the
repo can move or be deleted after installing. The script only does a literal
string replacement of the old command path in `settings.json` (backed up
first); every other setting in that shared file is left untouched. It refuses
to run (exit 1) until `host/install_relay.sh` has installed the shared
`buddy_harness.py`/`buddy_transport.py` the hook depends on. Re-run after
editing `claude_buddy_hook.py`.

Or run `./setup.sh` from the repo root to do all of the above in one pass
(relay + prompted hook installs + optional flash) -- see "Setup" below.

User-facing setup, safe samples, the versioned harness-neutral event contract,
and the requirements for adding another coding harness are documented in
`docs/buddy-display.md`. `host/buddy_harness.py` is the executable reference
client for that contract. Prefer it over teaching new adapters the legacy
color/text socket protocol directly.

`host/buddy_config.py` owns device-wide commands (`clock` and `clock-style`).
Both clients use `host/buddy_transport.py` for their short Unix-socket writes;
the transport knows nothing about lifecycle or display configuration.

`host/codex_buddy_hook.py` maps Codex lifecycle payloads into that contract.
`host/codex-hooks.json` is its reviewed hook definition, tracked as a
template (`__PYTHON3__` / `__CODEX_HOOKS_DIR__` placeholders, never a real
path). Run `host/install_codex_hooks.sh` to copy `codex_buddy_hook.py` to
the fixed location `~/.codex/hooks/` and render the template into
`~/.codex/hooks.json`; this never bakes this repo's checkout path into the
installed hook, so the repo can live anywhere (or move, or be deleted after
installing) without breaking it. It refuses to run (exit 1) until
`host/install_relay.sh` has installed the shared
`buddy_harness.py`/`buddy_transport.py` the hook depends on -- see the
"relay daemon" section above. Re-run after editing `codex_buddy_hook.py` --
Codex's hash-based hook trust is keyed on the installed copy's content, not
the repo's.

## Harness middle layer: the contract adapters should use

New harness integrations must use `host/buddy_harness.py`; do not open the USB
device and do not teach adapters the relay's `SESSION`/`ROW` wire formats. The
middle layer accepts a versioned, harness-neutral event:

```json
{"v":1,"op":"set","harness":"my-harness","session_id":"native-id","state":"working","label":"project"}
```

or the terminal form:

```json
{"v":1,"op":"end","harness":"my-harness","session_id":"native-id"}
```

The reference CLI is useful for development and manual checks:

```bash
python3 host/buddy_harness.py set my-harness session-42 working project
python3 host/buddy_harness.py end my-harness session-42
python3 host/buddy_config.py clock-style dots
```

`buddy_harness.py` validates events, sanitizes/truncates labels, hashes the raw
session id into a private relay id, applies the shared state color/text policy,
and performs short best-effort Unix-socket writes. A `set` sends the unchanged
`SESSION` command followed by a separate `ALERT <id> <0|1>` update; keeping
attention separate makes rolling relay upgrades safe. It never opens serial and
must never make a real harness hook fail because the display is unavailable.

Adapters own native lifecycle translation:

- session created/resumed and no turn active -> `set idle`
- prompt submitted or autonomous/tool work continues -> `set working`
- a real user permission decision is on screen -> `set approval`
- other required user input, if the harness distinguishes it -> `set waiting`
- compaction, if begin/end are observable -> `set compacting`, then `working`
- normal turn completion -> `set idle`
- unrecoverable turn failure -> `set error`
- session truly closed/deleted -> `end`

Use the harness's stable native session id, not a PID, cwd, title, or row
number. Repeated `set` calls for the same id are idempotent and update the same
row. Never send `end` merely because the user changed tabs. Conversely, every
adapter must send `end` on a definitive session-close event; real rows do not
expire just because they are quiet.

The relay owns allocation, eviction when all six rows are occupied, durable
state, serial reconnects, and replay. Its persisted table at
`~/.local/share/buddy-display/buddy-relay-state.json` uses only hashed ids and already-
formatted display text. After daemon/Mac restart it reloads that table; after
device reboot or USB replug it replays it. Therefore reconnect recovery applies
equally to Claude Code, Codex, and future harnesses without adapter-specific
enumeration. Only `#`-prefixed synthetic test ids expire after 30 minutes, and
manual tests must still send their matching `end`/`END` when inspection ends.
The same state file optionally stores the global `clock_style` (`arcs`, `dots`,
or `dotted-arcs`); `clock-style`
is not a harness lifecycle event, but it deliberately uses this middle layer so
no CLI or adapter opens serial. The relay sends
`CSTYLE <arcs|dots|dotted-arcs>` immediately
and before row replay on reconnect. With no saved selection, firmware uses
`BUDDY_CLOCK_STYLE_DEFAULT` (`dotted-arcs`).

If a harness lacks a native cancel/denial/failure hook, it may additionally
send `WATCH` through `buddy_harness.py` so the relay can apply a narrow,
harness-specific transcript fallback. Transcript formats are unstable and are
never part of the standard event contract; isolate their parsing in
`host/buddy_transcript.py` and add sanitized fixtures.

## How it works

**Firmware is a dumb renderer.** `BuddyProtocol.c` understands four line
formats over USB CDC serial:

```
ROW <index 0-5> <rrggbb> <text...>
CLOCK <hour 0-23> <minute 0-59> <second 0-59>
CSTYLE <arcs|dots|dotted-arcs>
ALERT <0|1>
```

It has **no notion of sessions, ids, staleness, or what a color/text means**
— `BuddyProtocol` writes validated values into the `BuddyData` model and
`BuddyStatusTile_Refresh()` paints it. `CLOCK` anchors the decorative hour/minute/
second perimeter on tile 1; the firmware advances it with monotonic time until
the relay's next sync. `CSTYLE` selects clean progress arcs, discrete
hour/minute dots, or dim background dots with progress arcs above them; it
carries no harness semantics. `ALERT` controls a generic backlight pulse without
teaching firmware what approval means. This is deliberate: all status policy (which
logical thing occupies which row, when something is stale enough to clear,
what "working" vs "waiting" looks like) was moved out of firmware and into
`buddy-relay.py` so it can change without a rebuild/reflash, and so the same
row pool can host things that aren't Claude Code sessions (a weather line,
etc.) — see the `project_buddy_display_architecture` note in this machine's
Claude Code memory for the full history if you have access to it.

**buddy-relay.py** is the only thing that opens the serial port. It runs as
a LaunchAgent (`com.buddy.relay`), holds the fd open, and listens on a Unix
socket for a higher-level, id-based protocol:

```
SESSION <id> <rrggbb> <text...>   create/update the row for <id>
ALERT <id> <0|1>                  set this id's attention flag
END <id>                          free <id>'s row
WATCH <id> <transcript_path> <profile> <label...>
UNWATCH <id>
CSTYLE <arcs|dots|dotted-arcs>
```

Its `RowManager` maps an arbitrary `<id>` to a row index (0..5), evicts the
oldest entry if the pool is full, atomically persists real rows in
`~/.local/share/buddy-display/buddy-relay-state.json`, and replays them whenever the daemon
or device reconnects (device reboot / USB replug always starts with a blank
row table). Real sessions live until `END`; only marked `#` synthetic/test rows
expire after ~30 minutes of silence. Its
`TranscriptWatcher` follows active harness transcript JSONL files for lifecycle
gaps and delegates complete records to `buddy_transcript.py` using the WATCH
profile. Claude recognizes structured denial, old and current ESC forms, and
terminal API/quota failures; Codex recognizes an `event_msg` whose payload is
`turn_aborted`. These recover a turn to idle when the harness has no hook for
it. Watches live for the row/session lifetime rather than an arbitrary short
timeout. Transcript formats are implementation details, so keep detection
narrow, structural, isolated by profile, and covered by sanitized fixtures in
`host/test_buddy_transcript.py`.

**host/claude_buddy_hook.py** is the active Claude Code hook adapter. Its
installed copy at `~/.claude/hooks/claude_buddy_hook.py` (see
`host/install_claude_hooks.sh` above) is registered in
`~/.claude/settings.json` under SessionStart/UserPromptSubmit/PreToolUse/etc.
It's fire-and-forget: on each hook event it
looks up the session's display name
(from `~/.claude/sessions/<pid>.json`, falling back to prompt text or cwd),
maps the native event to the shared `host/buddy_harness.py` contract, and
arms transcript recovery when needed. It never touches the serial port
directly and must never block a real hook.

A **hardware watchdog** (2s timeout) resets the chip if the main loop ever
stops calling `watchdog_update()`, as a last-resort recovery from an unknown
hang.

### Known toolchain footgun

On this RP2350 RISC-V (Hazard3) build, **`strncpy()`** and **`printf`/
`sscanf` with an `l`-length numeric conversion** (e.g. `%06lx` on an
`unsigned long`) have both been confirmed to reliably crash the firmware —
root cause never identified. `%s`/`%d` and `memcpy`-based copies
(`safe_bounded_copy()` in `BuddyData.c`) are confirmed safe. Don't
reintroduce either pattern.

Ring dots in `BuddyClock.c` must remain primitive-drawn. The original experiment
made 72 separate LVGL objects (12 hour dots plus 60 minute dots); on hardware
that build reset after ordinary `CLOCK`/row activity. In dot-clock mode the
current implementation draws each mark as one 6-pixel circular arc end-cap from
one `LV_EVENT_DRAW_MAIN` callback; arc-clock mode skips the callback and remains
clean. The callback must remain `DRAW_MAIN`, not `DRAW_POST`, so
`dotted-arcs` paints the dot face before LVGL draws the child arc widgets; do
not reverse that order or the dots will punch through the foreground arcs.
`get_arc_cap_area()` deliberately copies LVGL 8.1's private rounded-cap
placement. The cap diameter matches the seconds dot and the 6-pixel track.
Drawing only one cap avoids the elongated
shape produced by LVGL's minimum one-degree arc section, which contains an arc
body and two caps. It adds no objects, coordinate
tables, image masks, or canvas/framebuffer-sized allocation. Do not restore
per-dot objects or independently positioned circle sprites: on this 240-pixel
raster their integer centers visibly jump inward and outward around the ring.

## Building

cmake/ninja are **not** on `PATH` by default on this Mac — they're versioned
under `~/.pico-sdk/`:

```bash
export PATH="$HOME/.pico-sdk/cmake/v4.3.4/bin:$HOME/.pico-sdk/ninja/v1.13.2:$PATH"
cmake --build build
```

The build dir is already configured (`CMakeCache.txt` present); no need to
re-run `cmake -B build` unless `CMakeLists.txt` structure changed or `.c` files
were added/removed (`firmware/CMakeLists.txt` discovers sources at configure
time with `aux_source_directory`).
Output: `build/RP2350-LCD-1.28.elf` (and `.uf2`).

## Flashing

```bash
PICOTOOL=~/.pico-sdk/picotool/2.3.0/picotool/picotool
"$PICOTOOL" load -f -u -v -x build/RP2350-LCD-1.28.elf
```

`-f` forces the currently-running firmware to reboot into BOOTSEL mode over
USB — no physical BOOTSEL-button held reset needed as long as some firmware
is already running. Fall back to a physical BOOTSEL reset only if the board
is fully unresponsive.

**After reflashing, before touching the relay:** run the bounded raw-port test
in the recipe below. Never open the port from two processes at once — this has
hard-frozen the Mac before. Only restart the relay once the firmware is stable.
If crashing firmware receives the relay's replayed state immediately, the
relay can resend the same input on every reconnect and sustain a bootloop.

### Repeatable build -> flash -> smoke-test recipe

Use this when asked to "flash it again" or to prove that the ELF on disk is
actually running on the physical board. Start in this `C/` directory. If no
source changed and the existing ELF is known current, the build step may be
omitted; flashing the same ELF again is harmless.

1. Stop the relay so it releases the only serial fd. This is required for the
   raw smoke test, not merely a nicety:

   ```bash
   launchctl bootout gui/$(id -u)/com.buddy.relay
   ```

2. Build and flash. A successful flash ends with `Verifying Flash ... OK` and
   `The device was rebooted to start the application`:

   ```bash
   export PATH="$HOME/.pico-sdk/cmake/v4.3.4/bin:$HOME/.pico-sdk/ninja/v1.13.2:$PATH"
   cmake --build build
   "$HOME/.pico-sdk/picotool/2.3.0/picotool/picotool" \
     load -f -u -v -x build/RP2350-LCD-1.28.elf
   ```

3. Run one bounded raw-port test. The same process owns the port, writes the
   row and clock commands, reads firmware logs, clears its marked test row, and
   closes the fd:

   ```bash
   python3 - <<'PY'
   import glob, os, time

   ports = sorted(glob.glob("/dev/cu.usbmodem*"))
   if len(ports) != 1:
       raise SystemExit(f"expected exactly one display port, found: {ports}")

   fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
   try:
       os.write(fd, b"ROW 0 4CAF50 #flash: work\nCLOCK 12 34 56\n")
       time.sleep(3)  # the row should appear and the clock should update
       try:
           print(os.read(fd, 2048).decode(errors="replace"))
       except BlockingIOError:
           print("No serial log was ready; confirm the device stayed enumerated.")
       os.write(fd, b"ROW 0 000000 \n")
   finally:
       os.close(fd)
   PY
   ```

4. Always restart the relay, even if visual inspection failed, then confirm it
   reconnects and replays the real session rows:

   ```bash
   launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.buddy.relay.plist"
   tail -20 "$HOME/.local/share/buddy-display/logs/buddy-relay.log"
   ```

   Expected log sequence: `connected`, one or more `sent: 'ROW ...'` lines,
   `replayed ... known session row(s)`, and a `CLOCK` line. Also check that
   `/dev/cu.usbmodem*` still exists after several seconds;
   disappearance or repeated reconnects means the smoke test failed.

## Managing the relay daemon

```bash
# status
pgrep -fl buddy-relay.py
launchctl print gui/$(id -u)/com.buddy.relay

# start when unloaded
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.buddy.relay.plist"

# stop (required before any raw serial access)
launchctl bootout gui/$(id -u)/com.buddy.relay

# restart the process after installed Python source changes
launchctl kickstart -k gui/$(id -u)/com.buddy.relay

# reload after changing the LaunchAgent plist
launchctl bootout gui/$(id -u)/com.buddy.relay
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.buddy.relay.plist"

# verify/logs
tail -f ~/.local/share/buddy-display/logs/buddy-relay.log
```

Editing either active adapter in `host/` needs its installer re-run
(`install_claude_hooks.sh` / `install_codex_hooks.sh`) to redeploy the
change; adapters are invoked fresh per hook event, so no relay restart is
needed for that. Editing anything in `~/.local/share/buddy-display/` --
`buddy_style.py`, `buddy_transcript.py`, `buddy_harness.py`,
`buddy_transport.py`, or `buddy_relay.py` -- needs `host/install_relay.sh`
to redeploy it. That script always restarts the daemon as part of running,
even though only a `buddy_relay.py`/`buddy_style.py`/`buddy_transcript.py`
change strictly requires one (the daemon imports those; adapters re-import
`buddy_harness.py`/`buddy_transport.py` fresh each hook event, same as
their own files). The restart is harmless either way and does not clear
`buddy-relay-state.json`; rows and clock style are deliberately restored,
and active harnesses may immediately send fresh state.

## Testing by hand

**Syntax-check the Python side** before restarting the relay:

```bash
python3 -c "import ast; ast.parse(open('$HOME/.local/share/buddy-display/buddy-relay.py').read())"
python3 -c "import ast; ast.parse(open('$HOME/.claude/hooks/buddy-display.py').read())"
python3 -c "import ast; ast.parse(open('$HOME/.local/share/buddy-display/buddy_transcript.py').read())"
python3 - <<'EOF'
import os, sys; sys.path.insert(0, os.path.expanduser("~/.claude/hooks"))
import buddy_style
print(buddy_style.format_session("working", "myproj"))
EOF
```

**Drive the relay's socket directly** to exercise `SESSION`/`END`/`WATCH`
without going through a real Claude Code hook:

```python
import os, socket
def send(line):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(os.path.expanduser("~/.local/share/buddy-display/buddy-relay.sock"))
    s.sendall((line + "\n").encode())
    s.close()

send("SESSION #test01 4CAF50 #test: working")
send("END #test01")
```

Always send a matching `END` when done, and **prefix any manual/synthetic
test id or label with `#`** (e.g. `#test01`) so a leftover row is instantly
recognizable as test pollution rather than a real session, both in the log
and on the physical display. Then confirm cleanup:

```bash
grep -i "#test01" ~/.local/share/buddy-display/logs/buddy-relay.log | tail -5
```

**Watch what's actually going to the device** in real time:

```bash
tail -f ~/.local/share/buddy-display/logs/buddy-relay.log
```

Every line the relay sends over serial is logged as `sent: '...'`, along
with connect/reconnect/watch/expire events.

**Firmware-only smoke test** (no relay involved, single process): open the
port directly as shown in the "Flashing" section above and send raw `ROW`
lines to confirm the firmware itself parses and renders correctly, isolating
whether a bug is in the firmware or in the relay's translation layer.
