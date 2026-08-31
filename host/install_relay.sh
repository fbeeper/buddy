#!/usr/bin/env bash
# Installs the buddy-relay daemon to a harness-neutral fixed location
# (~/.local/share/buddy-display/) -- the relay serves Claude Code, Codex,
# and any future harness equally, so it has no business living under a
# harness-specific config directory.
#
# Also installs buddy_harness.py, buddy_transport.py, and buddy_config.py
# here: both hook adapters (Claude Code, Codex) import the first two, and
# all three are harness-neutral CLI/library code, so they belong in this
# shared location rather than duplicated per harness or left runnable only
# from inside the repo checkout.
#
# Copies buddy_relay.py, buddy_style.py, buddy_transcript.py,
# buddy_harness.py, buddy_transport.py, and buddy_config.py from this repo,
# writes the LaunchAgent plist, and (re)starts it. Re-run after editing any
# of those six files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/buddy-display"
PLIST="$HOME/Library/LaunchAgents/com.buddy.relay.plist"
PYTHON3_BIN="$(command -v python3)"

mkdir -p "$INSTALL_DIR/logs"

cp "$SCRIPT_DIR/buddy_relay.py" "$INSTALL_DIR/buddy-relay.py"
cp "$SCRIPT_DIR/buddy_style.py" "$INSTALL_DIR/buddy_style.py"
cp "$SCRIPT_DIR/buddy_transcript.py" "$INSTALL_DIR/buddy_transcript.py"
cp "$SCRIPT_DIR/buddy_harness.py" "$INSTALL_DIR/buddy_harness.py"
cp "$SCRIPT_DIR/buddy_transport.py" "$INSTALL_DIR/buddy_transport.py"
cp "$SCRIPT_DIR/buddy_config.py" "$INSTALL_DIR/buddy_config.py"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.buddy.relay</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3_BIN</string>
        <string>$INSTALL_DIR/buddy-relay.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/buddy-relay.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/buddy-relay.err.log</string>
</dict>
</plist>
PLIST

echo "Installed relay + LaunchAgent config pointing at $INSTALL_DIR"

launchctl bootout "gui/$(id -u)/com.buddy.relay" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Relay (re)started"
