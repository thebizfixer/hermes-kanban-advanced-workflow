# shellcheck shell=bash
# hermes_home.sh — resolve Hermes state directory (source, do not execute).
# Usage: source "$(dirname "$0")/lib/hermes_home.sh"
#
# Resolution order (cross-platform — Linux, macOS, Windows Git Bash, native Windows):
#   1. $HERMES_HOME           — explicit override (set by Hermes Agent itself)
#   2. $HERMES_STATE_DIR      — Hermes Agent v0.15+ state directory
#   3. $HOME/.hermes          — Linux, macOS, WSL2, Windows (Git Bash maps $HOME)
#   4. $USERPROFILE/.hermes   — Windows native (CMD, PowerShell, Hermes Desktop)
#                              Data directory per Hermes docs:
#                              https://hermes-agent.nousresearch.com/docs/user-guide/windows-native
#   5. $HOME/.hermes           — fallback (create if needed)

if [[ -n "${HERMES_HOME:-}" ]]; then
    :  # explicit override — use as-is
elif [[ -n "${HERMES_STATE_DIR:-}" ]]; then
    export HERMES_HOME="$HERMES_STATE_DIR"
elif [[ -n "${HOME:-}" && -d "$HOME/.hermes" ]]; then
    export HERMES_HOME="$HOME/.hermes"
elif [[ -n "${USERPROFILE:-}" && -d "$USERPROFILE/.hermes" ]]; then
    export HERMES_HOME="$USERPROFILE/.hermes"
elif [[ -n "${HOME:-}" ]]; then
    export HERMES_HOME="$HOME/.hermes"
elif [[ -n "${USERPROFILE:-}" ]]; then
    export HERMES_HOME="$USERPROFILE/.hermes"
else
    export HERMES_HOME="$HOME/.hermes"
fi

# Normalize Windows backslash paths to forward slashes.
# Safe no-op on Linux/macOS (no backslashes in paths).
# Prevents eval mangling, Python unicode escapes, and YAML corruption.
HERMES_HOME="${HERMES_HOME//\\//}"

# Cross-platform temp directory.
# On Windows (Git Bash or native), prefer $TEMP which maps to the user's temp.
# On Linux/macOS, $TMPDIR is standard; fall back to /tmp.
# Usage: source hermes_home.sh; echo "$KANBAN_TEMP"
if [[ -n "${KANBAN_TEMP:-}" ]]; then
    :  # explicit override
elif [[ -n "${TMPDIR:-}" ]]; then
    export KANBAN_TEMP="$TMPDIR"
elif [[ -n "${TEMP:-}" ]]; then
    export KANBAN_TEMP="$TEMP"
elif [[ -n "${TMP:-}" ]]; then
    export KANBAN_TEMP="$TMP"
elif [[ -d /tmp ]]; then
    export KANBAN_TEMP="/tmp"
else
    export KANBAN_TEMP="/tmp"  # Git Bash on Windows maps this
fi
