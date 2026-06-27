#!/usr/bin/env bash
# auto_unblock.sh — poll the kanban board and unblock cards whose parents are all done.
# Run via cron every 1m during execution (minimum supported cron interval). Handles the mechanical wave progression
# so the orchestrator doesn't need to manually unblock each wave.
#
# Usage:
#   bash scripts/auto_unblock.sh
#   bash scripts/auto_unblock.sh --dry-run    (report only, no unblock)
#   bash scripts/auto_unblock.sh --json       (machine-readable output)
#   bash scripts/auto_unblock.sh --stagger-sec 30   (sleep between unblocks — OAuth wave safety)
#   bash scripts/auto_unblock.sh --max-unblock 1    (cap unblocks per tick)

set -euo pipefail
export LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_cli_parse.sh
source "$SCRIPT_DIR/lib/kanban_cli_parse.sh"
# shellcheck source=lib/auto_unblock_core.sh
source "$SCRIPT_DIR/lib/auto_unblock_core.sh"

# ── HERMES_HOME resolution (cross-platform) ────────────────────────────
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

DRY_RUN=false
JSON_OUT=false
STAGGER_SEC="${KANBAN_UNBLOCK_STAGGER_SEC:-0}"
MAX_UNBLOCK="${KANBAN_UNBLOCK_MAX_PER_TICK:-0}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --json) JSON_OUT=true; shift ;;
        --stagger-sec) STAGGER_SEC="${2:-0}"; shift 2 ;;
        --max-unblock) MAX_UNBLOCK="${2:-0}"; shift 2 ;;
        *) shift ;;
    esac
done

# Default stagger for Cursor agent when auth-lock path is not yet proven healthy.
if [[ "$STAGGER_SEC" == "0" && "${KANBAN_CODING_AGENT:-}" == "agent" && "${KANBAN_UNBLOCK_STAGGER_SEC:-}" == "" ]]; then
    : # keep 0 — handshake/cache path preferred; operator sets KANBAN_UNBLOCK_STAGGER_SEC=30 as fallback
fi

# Optional OAuth pre-warm before releasing a wave (Cursor agent binary only).
PREWARM_FAILED=false
if [[ "$DRY_RUN" != true && "${KANBAN_PREWARM_ON_UNBLOCK:-1}" != "0" ]]; then
    # shellcheck source=lib/coding_agent_env.sh
    source "$SCRIPT_DIR/lib/coding_agent_env.sh"
    # shellcheck source=lib/coding_agent_auth_lock.sh
    source "$SCRIPT_DIR/lib/coding_agent_auth_lock.sh"
    if [[ -f "${REPO_ROOT:-$(pwd)}/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "${REPO_ROOT:-$(pwd)}/.env"
        set +a
    fi
    if [[ "${KANBAN_CODING_AGENT:-}" == "agent" ]]; then
        if ! prewarm_coding_agent_auth >/dev/null 2>&1; then
            PREWARM_FAILED=true
            echo "auto_unblock: prewarm_failed — not unblocking this tick" >&2
        fi
    fi
fi

if [[ "$PREWARM_FAILED" == true ]]; then
    LOG_DIR="$(kanban_logs_dir "$(pwd)")"
    mkdir -p "$LOG_DIR"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) prewarm_failed unblocked=0 stagger=${STAGGER_SEC}" >> "${LOG_DIR}/auto-unblock.log"
    exit 1
fi

TICK_ARGS=(--stagger-sec "$STAGGER_SEC")
[[ "$DRY_RUN" == true ]] && TICK_ARGS+=(--dry-run)
[[ "$JSON_OUT" == true ]] && TICK_ARGS+=(--json)
[[ "$MAX_UNBLOCK" -gt 0 ]] && TICK_ARGS+=(--max-unblock "$MAX_UNBLOCK")

# When KANBAN_BOARD is unset or default, scan all non-default boards.
# Timestamped boards (from kanban_handoff.py) don't persist the board env
# in the cron — auto_unblock must discover them.
if [[ -z "${KANBAN_BOARD:-}" || "$KANBAN_BOARD" == "default" ]]; then
  ALL_BOARDS="$(hermes kanban boards list 2>/dev/null | awk '{print $1}' | grep -vE '^(SLUG|default|$)')"
  if [[ -n "$ALL_BOARDS" ]]; then
    for BOARD in $ALL_BOARDS; do
      export KANBAN_BOARD="$BOARD"
      OUTPUT="$(kanban_auto_unblock_tick "${TICK_ARGS[@]}")"
      echo "[$BOARD] $OUTPUT"
    done
  fi
else
  OUTPUT="$(kanban_auto_unblock_tick "${TICK_ARGS[@]}")"
  echo "$OUTPUT"
fi

UNBLOCKED="$(echo "$OUTPUT" | sed -n 's/.*"unblocked":\([0-9]*\).*/\1/p')"
SKIPPED="$(echo "$OUTPUT" | sed -n 's/.*"skipped":\([0-9]*\).*/\1/p')"
ERRORS="$(echo "$OUTPUT" | sed -n 's/.*"errors":\([0-9]*\).*/\1/p')"
if [[ -z "$UNBLOCKED" ]]; then
    UNBLOCKED="$(echo "$OUTPUT" | sed -n 's/.*unblocked=\([0-9]*\).*/\1/p')"
    SKIPPED="$(echo "$OUTPUT" | sed -n 's/.*skipped=\([0-9]*\).*/\1/p')"
    ERRORS="$(echo "$OUTPUT" | sed -n 's/.*errors=\([0-9]*\).*/\1/p')"
fi
UNBLOCKED="${UNBLOCKED:-0}"
SKIPPED="${SKIPPED:-0}"
ERRORS="${ERRORS:-0}"

LOG_DIR="$(kanban_logs_dir "$(pwd)")"
mkdir -p "$LOG_DIR"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) unblocked=$UNBLOCKED skipped=$SKIPPED errors=$ERRORS stagger=${STAGGER_SEC} max_unblock=${MAX_UNBLOCK}" >> "${LOG_DIR}/auto-unblock.log"

exit 0
