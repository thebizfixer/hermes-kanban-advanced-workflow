#!/usr/bin/env bash
# worktree_setup.sh — Atomic worktree lifecycle for kanban workers.
#
# Usage:
#   bash worktree_setup.sh --task-id <id> --repo-root <path> [--config <file>] [--worktree-base <dir>]
#
# Outputs: WORKTREE_PATH=<path> on stdout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/worktree_include.sh
source "$SCRIPT_DIR/lib/worktree_include.sh"

TASK_ID=""
REPO_ROOT=""
WORKTREE_BASE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --task-id) TASK_ID="$2"; shift 2 ;;
        --repo-root) REPO_ROOT="$2"; shift 2 ;;
        --config) export HERMES_KANBAN_CONFIG="$2"; shift 2 ;;
        --worktree-base) WORKTREE_BASE="$2"; shift 2 ;;
        *) echo "[kanban-governance] ERROR: unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [ -z "$TASK_ID" ] || [ -z "$REPO_ROOT" ]; then
    echo "[kanban-governance] ERROR: --task-id and --repo-root are required" >&2
    exit 1
fi

if ! _load_branch_config "$REPO_ROOT"; then
    exit 1
fi

BASE="${WORKTREE_BASE:-${KANBAN_TEMP:-${TMPDIR:-${TEMP:-/tmp}}}}"
TASK_PREFIX="$(printf '%s' "$TASK_ID" | cut -c1-8)"
WORKTREE_PATH="${BASE}/wt-${TASK_PREFIX}"
ALLOWED_BRANCH="wt/${TASK_ID}"

cd "$REPO_ROOT"

# 1. Prune stale worktree registrations
git worktree prune 2>/dev/null || true

# 2. Detect existing worktree at target path
REUSE=false
if [ -d "$WORKTREE_PATH" ]; then
    if git worktree list --porcelain 2>/dev/null | grep -q "$WORKTREE_PATH"; then
        echo "[kanban-governance] Reusing stale worktree from prior reclaim: $WORKTREE_PATH" >&2
        REUSE=true
    else
        WORKTREE_PATH="${BASE}/wt-${TASK_PREFIX}-$(date +%s)"
        echo "[kanban-governance] Path occupied by non-worktree — using suffixed path: $WORKTREE_PATH" >&2
    fi
fi

# 3. Create worktree if needed
if [ "$REUSE" = false ]; then
    mkdir -p "$BASE"
    if git show-ref --verify --quiet "refs/heads/${ALLOWED_BRANCH}"; then
        git worktree add "$WORKTREE_PATH" "$ALLOWED_BRANCH" 2>/dev/null || \
        git worktree add -b "$ALLOWED_BRANCH" "$WORKTREE_PATH" HEAD
    else
        git worktree add -b "$ALLOWED_BRANCH" "$WORKTREE_PATH" HEAD
    fi
fi

# 3b. Copy gitignored kanban paths (.worktreeinclude) into the worktree
sync_worktree_include "$REPO_ROOT" "$WORKTREE_PATH"

# 4. Pre-trust workspace (cross-platform hash)
if [[ "$WORKTREE_PATH" =~ ^[A-Za-z]: ]]; then
    HASH=$(echo "$WORKTREE_PATH" | sed 's|:||; s|[/\\]|-|g')
else
    HASH=$(echo "$WORKTREE_PATH" | sed 's|^/||; s|/|-|g')
fi
TRUST_DIR="$HOME/.cursor/projects/$HASH"
mkdir -p "$TRUST_DIR"
touch "$TRUST_DIR/.workspace-trusted"

# 5. Install governance hooks
bash "$SCRIPT_DIR/install_pre_push_hook.sh" \
    "$WORKTREE_PATH" \
    "$ALLOWED_BRANCH" \
    "$WORKING_BRANCH" \
    "$TRIGGER_BRANCH"

bash "$SCRIPT_DIR/install_pre_commit_hook.sh" "$WORKTREE_PATH"

echo "WORKTREE_PATH=$WORKTREE_PATH"
