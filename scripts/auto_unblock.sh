#!/usr/bin/env bash
# auto_unblock.sh — poll the kanban board and unblock cards whose parents are all done.
# Run via cron every 1m during execution (minimum supported cron interval). Handles the mechanical wave progression
# so the orchestrator doesn't need to manually unblock each wave.
#
# Usage:
#   bash scripts/auto_unblock.sh
#   bash scripts/auto_unblock.sh --dry-run    (report only, no unblock)
#   bash scripts/auto_unblock.sh --json       (machine-readable output)

set -euo pipefail

# ── HERMES_HOME resolution (cross-platform) ────────────────────────────
# Hermes Agent canonical resolution: $HERMES_HOME → ~/.hermes (default).
# Cron scheduler sets HERMES_HOME in the environment; CLI users may rely on
# the default. Export it so child `hermes` processes find kanban.db.
# Ref: https://hermes-agent.nousresearch.com/docs/reference/environment-variables
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

DRY_RUN=false
JSON_OUT=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --json) JSON_OUT=true ;;
    esac
done

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
    PARENTS=$(echo "$DETAIL" | grep "parents:" | grep -oP 't_\w+' || true)

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

LOG_DIR="${HERMES_HOME}/kanban/logs"
mkdir -p "$LOG_DIR"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) unblocked=$UNBLOCKED skipped=$SKIPPED errors=$ERRORS" >> "${LOG_DIR}/auto-unblock.log"

exit 0
