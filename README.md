# RP2350 round buddy display

> [!WARNING]
> Use this project entirely at your own risk. It is experimental firmware and
> host tooling, provided without warranty, and can interact directly with USB,
> serial devices, display hardware, and background services. The project was
> written with the help of coding harnesses, starting from the board samples
> distributed by Waveshare through the
> [RP2350-LCD-1.28 product wiki](https://www.waveshare.com/wiki/RP2350-LCD-1.28).
> Review the source and understand the build, flash, and daemon procedures
> before using or redistributing it.

Firmware and host-side integration notes for a Waveshare
RP2350-LCD-1.28-B used as a six-row coding-session status display.

The board is intentionally a dumb renderer. A single host daemon owns its
USB serial port, assigns logical sessions to rows, and restores them after a
device reconnect. Coding harnesses do not open the serial device themselves.

Run `./setup.sh` to install and start the relay daemon, optionally wire up
the Claude Code and/or Codex hooks, and optionally build and flash a
connected board. Safe to re-run any time. `./uninstall.sh` reverses it --
stops the daemon, and removes everything `setup.sh` installed, including the
buddy-hook entries it added to each harness's settings.

Start with [docs/buddy-display.md](docs/buddy-display.md) for:

- a two-minute demo through the running daemon;
- the daemon and firmware protocols;
- setup and troubleshooting;
- the standard, harness-neutral event contract; and
- the lifecycle behavior a good Claude Code, Codex, or other adapter needs.

The reusable middle layer is `host/buddy_harness.py`. Claude Code and Codex
use the thin adapters `host/claude_buddy_hook.py` and
`host/codex_buddy_hook.py`; Codex's hook definition is `host/codex-hooks.json`.
Tested fallbacks for lifecycle gaps such as Escape cancellation and terminal
quota errors are isolated by harness in `host/buddy_transcript.py`.

Repository-maintainer and hardware build/flash notes are in [AGENTS.md](AGENTS.md).

## License

Original project code is available under the MIT license in [LICENSE](LICENSE).
The Waveshare LCD and QMI8658 driver portions are redistributed under Apache
License 2.0, based on Waveshare's explicitly licensed official components for
those devices. Bundled dependencies, the generated JetBrains Mono font, and
the embedded dog photograph remain under their respective terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). In particular, the photograph
is Copyright (c) 2026 fbeeper and licensed for reuse under CC BY 4.0.
