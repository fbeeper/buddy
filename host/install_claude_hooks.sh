#!/usr/bin/env bash
# Copies the Claude Code buddy-display hook adapter to a fixed,
# repo-independent location (~/.claude/hooks/), and repoints
# ~/.claude/settings.json's buddy-hook command entries there.
#
# buddy_harness.py and buddy_transport.py are NOT copied here -- they're
# harness-neutral (Codex's adapter uses the identical files), so they live
# once in ~/.local/share/buddy-display/ (see install_relay.sh) and this
# adapter imports them from there.
#
# ~/.claude/settings.json is a shared file with unrelated settings (model,
# theme, plugins, ...), so this only does a literal string replacement of
# the old absolute repo path -> the new fixed path; it never rewrites or
# reformats the rest of the file. A timestamped backup is made first.
#
# Re-run after editing claude_buddy_hook.py.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
OLD_PATH="$SCRIPT_DIR/claude_buddy_hook.py"
NEW_PATH="$INSTALL_DIR/claude_buddy_hook.py"

if [ ! -f "$HOME/.local/share/buddy-display/buddy_harness.py" ]; then
  echo "Run host/install_relay.sh first -- it installs buddy_harness.py and" \
       "buddy_transport.py, which this hook imports." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/claude_buddy_hook.py" "$INSTALL_DIR/"
echo "Installed hook script to $INSTALL_DIR"

if [ ! -f "$SETTINGS" ]; then
  echo "No $SETTINGS found; register the SessionStart/UserPromptSubmit/etc" \
       "hooks manually, pointing their command at $NEW_PATH"
  exit 0
fi

BACKUP="$SETTINGS.bak.$(date +%s)"
cp "$SETTINGS" "$BACKUP"

python3 - "$SETTINGS" "$OLD_PATH" "$NEW_PATH" <<'PY'
import sys, pathlib
settings_path, old_path, new_path = sys.argv[1:4]
text = pathlib.Path(settings_path).read_text()
n = text.count(old_path)
if n:
    pathlib.Path(settings_path).write_text(text.replace(old_path, new_path))
    print(f"Replaced {n} occurrence(s) of the repo path in {settings_path}")
else:
    print(f"No occurrences of {old_path} found in {settings_path} (already migrated?)")
PY

echo "Backup saved at $BACKUP"
