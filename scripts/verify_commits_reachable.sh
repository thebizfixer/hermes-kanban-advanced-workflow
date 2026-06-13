#!/usr/bin/env bash
# verify_commits_reachable.sh — confirm all completed kanban card commits
# are reachable from staging. Catches worktree-cleanup-before-merge (E016).
#
# Run during final audit, after merging all branches to staging.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/verify_commits_reachable.sh <plan_id>
#   bash hermes-kanban-advanced-workflow/scripts/verify_commits_reachable.sh <plan_id> --json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_PARSE="$SCRIPT_DIR/lib/cli_output_parse.py"
source "$SCRIPT_DIR/lib/kanban_config.sh"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! _load_branch_config "$REPO_ROOT"; then
    exit 1
fi
INTEGRATION_BRANCH="$WORKING_BRANCH"

PLAN_ID="${1:-}"
JSON_OUT=false
[[ "${2:-}" == "--json" ]] && JSON_OUT=true

if [ -z "$PLAN_ID" ]; then
    echo "Usage: verify_commits_reachable.sh <plan_id>" >&2
    exit 1
fi

MISSING=0
FOUND=0

# Find all done/archived cards for this plan and extract commit hashes
CARD_IDS=$(hermes kanban list 2>/dev/null | grep '✓' | awk '{print $2}' || true)
[ -z "$CARD_IDS" ] && CARD_IDS=$(hermes kanban list 2>/dev/null | grep 'archived' | awk '{print $2}' || true)

for tid in $CARD_IDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null || true)
    # Only check cards belonging to this plan
    if ! echo "$BODY" | grep -q "plan_id: $PLAN_ID"; then
        continue
    fi
    
    # Extract commit hash from completion summary
    COMMIT=$(python3 "$CLI_PARSE" commit-hash --text "$BODY" 2>/dev/null || true)
    if [ -z "$COMMIT" ]; then
        # Some cards (benchmark, audit) have no commits — skip
        TITLE=$(echo "$BODY" | grep "Task $tid:" | head -1)
        if echo "$TITLE" | grep -qiE 'benchmark|audit|gate|root'; then
            continue
        fi
        # Card has no commit hash — flag if it has an agent block (should have committed)
        if echo "$BODY" | grep -q '```agent'; then
            echo "WARN: $tid has agent block but no commit hash found in summary" >&2
            continue
        fi
        continue
    fi
    
    # Check if commit is reachable from integration branch (working_branch from config)
    if git merge-base --is-ancestor "$COMMIT" "$INTEGRATION_BRANCH" 2>/dev/null; then
        ((FOUND++)) || true
    # Fallback: check cherry-pick trailer (from git cherry-pick -x)
    elif git log "$INTEGRATION_BRANCH" --format="%B" 2>/dev/null | grep -q "(cherry picked from commit ${COMMIT})"; then
        ((FOUND++)) || true
    else
        echo "MISSING: $tid commit $COMMIT not on $INTEGRATION_BRANCH" >&2
        ((MISSING++)) || true
    fi
done

if [ "$JSON_OUT" = true ]; then
    echo "{\"found\":$FOUND,\"missing\":$MISSING}"
else
    echo "verify_commits: found=$FOUND missing=$MISSING"
fi

[ "$MISSING" -eq 0 ] && exit 0 || exit 1
