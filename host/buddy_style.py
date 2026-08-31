"""Shared display styling for the buddy status device.

The firmware knows nothing about what "working" or "waiting" mean -- it just
renders whatever (hex color, text) a SESSION line gives it. All the actual
policy of what each state looks like lives here, in one place, so it's a
plain Python edit (no firmware rebuild/reflash) to add a state, rename one,
or change a color, and both buddy-display.py (the hook adapter) and
buddy-relay.py (which needs to construct an "idle" line on its own when a
transcript watch resolves a stuck state) stay in sync automatically.
"""

# Material-ish palette, matching the LVGL colors the firmware used to pick
# itself before this became host-controlled.
COLORS = {
    "idle": "3FAEDA",
    "working": "4CAF50",    # green
    "waiting": "80BB64",
    "approval": "D4301B",
    "compacting": "FDFB1D",
}

# Display word shown on screen, which can differ from the internal state
# name used elsewhere in these scripts (e.g. "waiting" reads too close to
# "working" at a glance on a small screen, so it displays as "approval").
DISPLAY_WORDS = {
    "idle": "idle",
    "working": "work",
    "waiting": "appr",
    "approval": "appr",
    "compacting": "comp",
}

LABEL_CHARS = 6  # how much of the label fits before the ": <word>" suffix


def harness_prefix(harness: str) -> str:
    """Two-letter tag shown before the label, derived from the harness id.

    No harness registers a prefix explicitly -- it's always the first two
    characters of the harness id, uppercased. Keep in sync with
    host/buddy_harness.py's harness_prefix().
    """
    return harness[:2].upper()


def format_session(state: str, label: str, harness: str = "??") -> tuple:
    """Returns (hex_color, display_text) for a SESSION line, given an
    internal state name, a session label, and the harness id."""
    color = COLORS.get(state, COLORS["idle"])
    word = DISPLAY_WORDS.get(state, state)
    prefix = harness_prefix(harness)
    text = f"{prefix}|{label[:LABEL_CHARS]}: {word}"
    return color, text
