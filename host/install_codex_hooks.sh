#!/usr/bin/env bash
# Installs the Codex buddy-display hook to a fixed, repo-independent
# location so ~/.codex/hooks.json never depends on where this repo is
# checked out. Re-run after editing codex_buddy_hook.py.
#
# buddy_harness.py and buddy_transport.py are NOT copied here -- they're
# harness-neutral (Claude Code's adapter uses the identical files), so they
# live once in ~/.local/share/buddy-display/ (see install_relay.sh) and this
# adapter imports them from there.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.codex/hooks"
PYTHON3_BIN="$(command -v python3)"

if [ ! -f "$HOME/.local/share/buddy-display/buddy_harness.py" ]; then
  echo "Run host/install_relay.sh first -- it installs buddy_harness.py and" \
       "buddy_transport.py, which this hook imports." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/codex_buddy_hook.py" "$INSTALL_DIR/"

sed \
  -e "s#__PYTHON3__#$PYTHON3_BIN#g" \
  -e "s#__CODEX_HOOKS_DIR__#$INSTALL_DIR#g" \
  "$SCRIPT_DIR/codex-hooks.json" > "$HOME/.codex/hooks.json"

echo "Installed hook scripts to $INSTALL_DIR"
echo "Wrote $HOME/.codex/hooks.json"
