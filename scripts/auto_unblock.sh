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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_cli_parse.sh
source "$SCRIPT_DIR/lib/kanban_cli_parse.sh"

# ── HERMES_HOME resolution (cross-platform) ────────────────────────────
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

DRY_RUN=false
JSON_OUT=false
STAGGER_SEC="${KANBAN_UNBLOCK_STAGGER_SEC:-0}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --json) JSON_OUT=true; shift ;;
        --stagger-sec) STAGGER_SEC="${2:-0}"; shift 2 ;;
        *) shift ;;
    esac
done

# Optional OAuth pre-warm before releasing a wave (Cursor agent binary only).
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
        prewarm_coding_agent_auth >/dev/null 2>&1 || true
    fi
fi

UNBLOCKED=0
SKIPPED=0
ERRORS=0
RESULTS=""

# Get all blocked cards with their parents
BLOCKED_LIST=$(hermes kanban list 2>/dev/null | grep '⊘' | awk '{print $2}' || true)

if [ -z "$BLOCKED_LIST" ]; then
    [ "$JSON_OUT" = true ] && echo '{"unblocked":0,"skipped":0,"errors":0,"message":"no blocked cards"}'
    exit 0
fi

for tid in $BLOCKED_LIST; do
    # Get card details
    DETAIL=$(hermes kanban show "$tid" 2>/dev/null || true)
    if [ -z "$DETAIL" ]; then
        ((ERRORS++)) || true
        RESULTS+="{\"task\":\"$tid\",\"status\":\"error\",\"reason\":\"show failed\"}"$'\n'
        continue
    fi

    # Extract parent IDs
    PARENTS=$(echo "$DETAIL" | grep "parents:" | kanban_extract_task_ids)

    # If no parents, skip — unblocking parentless blocked cards is the orchestrator's job
    if [ -z "$PARENTS" ]; then
        ((SKIPPED++)) || true
        RESULTS+="{\"task\":\"$tid\",\"status\":\"skipped\",\"reason\":\"no parents\"}"$'\n'
        continue
    fi

    # Check if all parents are done
    ALL_DONE=true
    for pid in $PARENTS; do
        PSTATUS=$(hermes kanban show "$pid" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}' || true)
        if [ "$PSTATUS" != "done" ]; then
            ALL_DONE=false
            break
        fi
    done

    if [ "$ALL_DONE" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            RESULTS+="{\"task\":\"$tid\",\"status\":\"would_unblock\",\"parents_done\":true}"$'\n'
        else
            if hermes kanban unblock "$tid" 2>/dev/null; then
                ((UNBLOCKED++)) || true
                RESULTS+="{\"task\":\"$tid\",\"status\":\"unblocked\",\"parents_done\":true}"$'\n'
                if [[ "$STAGGER_SEC" =~ ^[0-9]+$ && "$STAGGER_SEC" -gt 0 ]]; then
                    sleep "$STAGGER_SEC"
                fi
            else
                ((ERRORS++)) || true
                RESULTS+="{\"task\":\"$tid\",\"status\":\"error\",\"reason\":\"unblock command failed\"}"$'\n'
            fi
        fi
    else
        ((SKIPPED++)) || true
    fi
done

if [ "$JSON_OUT" = true ]; then
    echo "{\"unblocked\":$UNBLOCKED,\"skipped\":$SKIPPED,\"errors\":$ERRORS}"
else
    echo "auto_unblock: unblocked=$UNBLOCKED skipped=$SKIPPED errors=$ERRORS"
    if [ "$DRY_RUN" = true ] && [ "$UNBLOCKED" -gt 0 ]; then
        echo "  (dry-run — would have unblocked $UNBLOCKED cards)"
    fi
fi

LOG_DIR="$(kanban_logs_dir "$(pwd)")"
mkdir -p "$LOG_DIR"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) unblocked=$UNBLOCKED skipped=$SKIPPED errors=$ERRORS stagger=${STAGGER_SEC}" >> "${LOG_DIR}/auto-unblock.log"

exit 0
