#!/usr/bin/env bash
# Reverses everything setup.sh (via install_relay.sh, install_claude_hooks.sh,
# install_codex_hooks.sh) put on this machine: the relay daemon + LaunchAgent,
# both hook adapters, and the buddy-hook entries they added to each harness's
# settings. Safe to re-run; each step is a no-op if already removed.
#
# Firmware on the board itself is untouched -- this only removes host-side
# install state.
set -euo pipefail

confirm() {
  local prompt="$1"
  if [ ! -t 0 ]; then
    echo "$prompt [non-interactive, skipping]"
    return 1
  fi
  local reply
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

RELAY_DIR="$HOME/.local/share/buddy-display"
PLIST="$HOME/Library/LaunchAgents/com.buddy.relay.plist"
CLAUDE_HOOK="$HOME/.claude/hooks/claude_buddy_hook.py"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
CODEX_HOOK="$HOME/.codex/hooks/codex_buddy_hook.py"
CODEX_HOOKS_JSON="$HOME/.codex/hooks.json"

echo "== 1. Relay daemon =="
if [ -d "$RELAY_DIR" ] || [ -f "$PLIST" ]; then
  if confirm "Stop the relay and remove $RELAY_DIR and $PLIST?"; then
    launchctl bootout "gui/$(id -u)/com.buddy.relay" 2>/dev/null || true
    rm -f "$PLIST"
    rm -rf "$RELAY_DIR"
    echo "Removed."
  fi
else
  echo "Nothing installed."
fi

echo
echo "== 2. Claude Code hook =="
if [ -f "$CLAUDE_HOOK" ] || { [ -f "$CLAUDE_SETTINGS" ] && grep -q "claude_buddy_hook.py" "$CLAUDE_SETTINGS"; }; then
  if confirm "Remove $CLAUDE_HOOK and its entries in $CLAUDE_SETTINGS?"; then
    rm -f "$CLAUDE_HOOK"
    if [ -f "$CLAUDE_SETTINGS" ]; then
      BACKUP="$CLAUDE_SETTINGS.bak.$(date +%s)"
      cp "$CLAUDE_SETTINGS" "$BACKUP"
      python3 - "$CLAUDE_SETTINGS" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

hooks = data.get("hooks", {})
removed = 0
for event in list(hooks.keys()):
    new_groups = []
    for group in hooks[event]:
        inner = group.get("hooks", [])
        kept = [h for h in inner if "claude_buddy_hook.py" not in h.get("command", "")]
        removed += len(inner) - len(kept)
        if kept:
            group = dict(group)
            group["hooks"] = kept
            new_groups.append(group)
        # else: this group had only the buddy hook -- drop the whole group
    if new_groups:
        hooks[event] = new_groups
    else:
        del hooks[event]

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)
    f.write("\n")

print(f"Removed {removed} hook entrie(s) from {path}; every other setting is untouched")
PY
      echo "Backup saved at $BACKUP"
    fi
  fi
else
  echo "Nothing installed."
fi

echo
echo "== 3. Codex hook =="
if [ -f "$CODEX_HOOK" ] || [ -f "$CODEX_HOOKS_JSON" ]; then
  if confirm "Remove $CODEX_HOOK and $CODEX_HOOKS_JSON?"; then
    rm -f "$CODEX_HOOK"
    rm -f "$CODEX_HOOKS_JSON"
    rmdir "$(dirname "$CODEX_HOOK")" 2>/dev/null || true
    echo "Removed."
  fi
else
  echo "Nothing installed."
fi

echo
echo "Uninstall complete."
