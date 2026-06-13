#!/usr/bin/env bash
# worktree_audit.sh — Cross-reference git worktrees with kanban board.
#
# Runs when the board keeper signals completion. Answers:
#   "Is any work lost in a worktree that should have been merged?"
#
# For each worktree, determines:
#   - safe-to-clean   — card done + worktree merged to staging
#   - needs-salvage   — card done + worktree has unmerged commits
#   - potential-loss  — no card found + worktree has uncommitted changes
#   - stale           — no card + clean + >1hr old
#
# Usage:
#   bash worktree_audit.sh
#   bash worktree_audit.sh --staging staging
#
# Exit codes:
#   0 — All worktrees clean (safe to proceed)
#   1 — One or more worktrees need attention

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_PARSE="$SCRIPT_DIR/lib/cli_output_parse.py"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$REPO_ROOT"

if ! _load_branch_config "$REPO_ROOT"; then
    exit 1
fi
STAGING_BRANCH="$WORKING_BRANCH"

red()    { echo -e "\033[31m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --staging) STAGING_BRANCH="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "=== Worktree Audit ==="
echo "Repo: $REPO_ROOT"
echo "Staging: $STAGING_BRANCH"
echo ""

SAFE=0
NEEDS_SALVAGE=0
POTENTIAL_LOSS=0
STALE=0
IN_USE=0
TOTAL=0

# ── Get kanban board state ──────────────────────────────────────────────
BOARD_JSON=""
if hermes kanban list &>/dev/null 2>&1; then
    BOARD_JSON=$(hermes kanban list 2>/dev/null || echo "")
else
    yellow "hermes CLI not available — cannot cross-reference with kanban board."
    BOARD_JSON=""
fi

# ── Helper: find card by worktree path ──────────────────────────────────
find_card_for_worktree() {
    local wt_path="$1"
    if [[ -z "$BOARD_JSON" ]]; then
        echo ""
        return
    fi
    # Search board output for lines containing this worktree path
    echo "$BOARD_JSON" | while IFS= read -r line; do
        if echo "$line" | grep -q "$wt_path"; then
            echo "$line" | awk '{print $2}'  # task ID is second field
            return
        fi
    done
    echo ""
}

# ── Check card status ──────────────────────────────────────────────────
get_card_status() {
    local task_id="$1"
    [[ -z "$task_id" ]] && echo "unknown" && return
    hermes kanban show "$task_id" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}' || echo "unknown"
}

# ── Iterate worktrees ──────────────────────────────────────────────────
while IFS= read -r wt_line; do
    [[ -z "$wt_line" ]] && continue
    WT_PATH=$(echo "$wt_line" | awk '{print $1}')
    WT_BRANCH=$(python3 "$CLI_PARSE" worktree-branch --text "$wt_line" 2>/dev/null || echo "detached")
    ((TOTAL++))

    echo "Worktree: $WT_PATH  [$WT_BRANCH]"

    # Find corresponding card
    CARD_ID=""
    if [[ -n "$BOARD_JSON" ]]; then
        # Try matching by worktree path in board
        CARD_ID=$(echo "$BOARD_JSON" | grep "$WT_PATH" | head -1 | awk '{print $2}' || echo "")
    fi

    # Check if worktree has uncommitted changes
    DIRTY=false
    UNCOMMITTED_FILES=""
    if [[ -d "$WT_PATH" ]]; then
        UNCOMMITTED_FILES=$(git -C "$WT_PATH" status --short 2>/dev/null || echo "")
        [[ -n "$UNCOMMITTED_FILES" ]] && DIRTY=true
    fi

    # Check if worktree is merged to staging
    MERGED=false
    AHEAD=0
    if [[ -d "$WT_PATH" ]]; then
        AHEAD=$(git -C "$WT_PATH" rev-list --count "${STAGING_BRANCH}..HEAD" 2>/dev/null || echo "-1")
        [[ "$AHEAD" == "0" ]] && MERGED=true
    fi

    # Check if worktree is old (>1hr)
    STALE_FLAG=false
    [[ -n "$(find "$WT_PATH" -maxdepth 0 -mmin +60 2>/dev/null)" ]] && STALE_FLAG=true

    # Check if in use by active process
    IN_USE_FLAG=false
    pgrep -f "$WT_PATH" &>/dev/null && IN_USE_FLAG=true

    # ── Classify ────────────────────────────────────────────────────────
    if [[ "$IN_USE_FLAG" == "true" ]]; then
        yellow "  → IN USE — active process running in worktree"
        ((IN_USE++))
        echo ""
        continue
    fi

    if [[ -n "$CARD_ID" ]]; then
        CARD_STATUS=$(get_card_status "$CARD_ID")
        
        if [[ "$CARD_STATUS" == "done" ]]; then
            if [[ "$MERGED" == "true" ]] && [[ "$DIRTY" == "false" ]]; then
                green "  → SAFE-TO-CLEAN — card $CARD_ID done, clean, merged"
                ((SAFE++))
            elif [[ "$MERGED" == "false" ]]; then
                yellow "  → NEEDS-SALVAGE — card $CARD_ID done but $AHEAD commits ahead of $STAGING_BRANCH"
                git -C "$WT_PATH" log --oneline "${STAGING_BRANCH}..HEAD" 2>/dev/null | head -5
                ((NEEDS_SALVAGE++))
            elif [[ "$DIRTY" == "true" ]]; then
                yellow "  → NEEDS-SALVAGE — card $CARD_ID done but has uncommitted changes:"
                echo "$UNCOMMITTED_FILES" | head -5
                ((NEEDS_SALVAGE++))
            fi
        elif [[ "$CARD_STATUS" == "blocked" || "$CARD_STATUS" == "crashed" || "$CARD_STATUS" == "timed_out" ]]; then
            yellow "  → NEEDS-SALVAGE — card $CARD_ID is $CARD_STATUS, check for salvageable work"
            if [[ "$AHEAD" -gt 0 ]]; then
                echo "    $AHEAD unmerged commit(s) in worktree"
            fi
            if [[ "$DIRTY" == "true" ]]; then
                echo "    Uncommitted files present"
            fi
            ((NEEDS_SALVAGE++))
        else
            # Card is running/ready/todo — worktree still active
            green "  → ACTIVE — card $CARD_ID is $CARD_STATUS"
            ((IN_USE++))
        fi
    else
        # No card found
        if [[ "$DIRTY" == "true" ]]; then
            red "  → POTENTIAL-LOSS — no card found, uncommitted changes present:"
            echo "$UNCOMMITTED_FILES" | head -5
            ((POTENTIAL_LOSS++))
        elif [[ "$STALE_FLAG" == "true" ]]; then
            yellow "  → STALE — no card, clean, >1hr old. Safe to clean."
            ((STALE++))
        else
            echo "  → RECENT — no card, clean, but modified <1hr ago"
            ((STALE++))  # Counting as stale since no card
        fi
    fi
    echo ""
done <<< "$(git worktree list 2>/dev/null | tail -n +2)"

# ── Summary ─────────────────────────────────────────────────────────────
echo "=== Audit Summary ==="
echo "Total:      $TOTAL worktrees"
echo "Safe:       $SAFE — can clean"
echo "Stale:      $STALE — no card, stale — can clean"
echo "In use:     $IN_USE — active — do not touch"
echo "Salvage:    $NEEDS_SALVAGE — card done, work not merged"
echo "⚠ Lost risk: $POTENTIAL_LOSS — no card, uncommitted changes"

echo ""
if [[ $POTENTIAL_LOSS -gt 0 ]]; then
    red "→ BLOCKED: $POTENTIAL_LOSS worktree(s) with potential lost work. Review before cleanup."
    exit 1
elif [[ $NEEDS_SALVAGE -gt 0 ]]; then
    yellow "→ $NEEDS_SALVAGE worktree(s) need salvage — merge before cleanup."
    exit 1
else
    CLEANABLE=$(( SAFE + STALE ))
    green "→ All $TOTAL worktrees accounted for. $CLEANABLE safe to clean. Ready for cleanup."
    exit 0
fi
