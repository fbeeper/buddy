#!/usr/bin/env bash
# One-shot project setup: installs + starts the buddy-relay daemon, offers to
# wire up the Claude Code and/or Codex hooks, and offers to build + flash a
# connected board. Safe to re-run any time (each step is idempotent).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_DIR="$SCRIPT_DIR/host"

confirm() {
  # confirm "question" -- returns 0 (yes) on empty/interactive default-yes
  # answer, 1 otherwise. Defaults to "no" when not running in a terminal.
  local prompt="$1"
  if [ ! -t 0 ]; then
    echo "$prompt [non-interactive, skipping]"
    return 1
  fi
  local reply
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

echo "== 1. Relay daemon =="
"$HOST_DIR/install_relay.sh"

echo
echo "== 2. Coding-harness hooks =="
if confirm "Install/refresh the Claude Code hook?"; then
  "$HOST_DIR/install_claude_hooks.sh"
fi
if confirm "Install/refresh the Codex hook?"; then
  "$HOST_DIR/install_codex_hooks.sh"
fi

echo
echo "== 3. Firmware flash =="
export PATH="$HOME/.pico-sdk/cmake/v4.3.4/bin:$HOME/.pico-sdk/ninja/v1.13.2:$PATH"
PICOTOOL="$HOME/.pico-sdk/picotool/2.3.0/picotool/picotool"

shopt -s nullglob
PORTS=(/dev/cu.usbmodem*)
shopt -u nullglob

if [ "${#PORTS[@]}" -eq 0 ] || [ -z "${PORTS[0]}" ]; then
  echo "No board detected on /dev/cu.usbmodem*; skipping flash."
elif confirm "Board detected at ${PORTS[0]}. Build and flash it?"; then
  echo "Stopping relay so it releases the serial port..."
  launchctl bootout "gui/$(id -u)/com.buddy.relay" 2>/dev/null || true

  cmake --build "$SCRIPT_DIR/build"
  "$PICOTOOL" load -f -u -v -x "$SCRIPT_DIR/build/RP2350-LCD-1.28.elf"

  echo "Restarting relay..."
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.buddy.relay.plist"
fi

echo
echo "Setup complete."
