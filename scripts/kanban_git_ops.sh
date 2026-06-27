#!/usr/bin/env bash
# kanban_git_ops.sh — governed git operations for kanban card worktrees.
#
# Usage:
#   bash scripts/kanban_git_ops.sh setup --task-id ID --repo-root PATH
#   bash scripts/kanban_git_ops.sh integrate --task-id ID --parent-keys card2,card5
#   bash scripts/kanban_git_ops.sh restore-plan --plan-id ID --worktree PATH
#   bash scripts/kanban_git_ops.sh freshness --worktree PATH
#   bash scripts/kanban_git_ops.sh audit
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/plan_paths.sh
source "$SCRIPT_DIR/lib/plan_paths.sh"

CMD="${1:-}"
shift || true

case "$CMD" in
  setup)
    TASK_ID=""
    REPO_ROOT=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --task-id) TASK_ID="${2:-}"; shift 2 ;;
        --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ -z "$TASK_ID" || -z "$REPO_ROOT" ]] && { echo "usage: setup --task-id ID --repo-root PATH" >&2; exit 2; }
    OUT="$(bash "$SCRIPT_DIR/worktree_setup.sh" --task-id "$TASK_ID" --repo-root "$REPO_ROOT")"
    echo "$OUT"
    ;;
  integrate)
    TASK_ID=""
    PARENT_KEYS=""
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --task-id) TASK_ID="${2:-}"; shift 2 ;;
        --parent-keys) PARENT_KEYS="${2:-}"; shift 2 ;;
        --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ -z "$TASK_ID" || -z "$PARENT_KEYS" ]] && { echo "usage: integrate --task-id ID --parent-keys k1,k2" >&2; exit 2; }
    _load_branch_config "$REPO_ROOT" || exit 1
    PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}"
    MEM="${REPO_ROOT}/.hermes/kanban/memory/${PLAN_ID}.json"
    WS="$(hermes kanban --board "${KANBAN_BOARD:-default}" show "$TASK_ID" 2>/dev/null | grep 'workspace:' | head -1 | sed 's/.*@ //' | xargs)"
    [[ -z "$WS" || ! -d "$WS" ]] && { echo "WORKTREE missing for $TASK_ID" >&2; exit 1; }
    IFS=',' read -r -a KEYS <<< "$PARENT_KEYS"
    for key in "${KEYS[@]}"; do
      key="$(echo "$key" | xargs)"
      [[ -z "$key" ]] && continue
      BRANCH="$(python3 - "$MEM" "$key" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
    branches = data.get("card_branches") or {}
    print(branches.get(key, ""))
except Exception:
    print("")
PY
)"
      [[ -z "$BRANCH" ]] && continue
      TID="$(python3 - "$MEM" "$key" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
    ids = data.get("card_task_ids") or data.get("task_ids_by_key") or {}
    print(ids.get(key, ""))
except Exception:
    print("")
PY
)"
      [[ -z "$TID" ]] && continue
      PWS="$(hermes kanban --board "${KANBAN_BOARD:-default}" show "$TID" 2>/dev/null | grep 'workspace:' | head -1 | sed 's/.*@ //' | xargs)"
      [[ -z "$PWS" || ! -d "$PWS" ]] && continue
      PB="$(cd "$PWS" && git branch --show-current 2>/dev/null || true)"
      [[ -z "$PB" ]] && continue
      cd "$REPO_ROOT"
      git remote add "wt-$TID" "$PWS" 2>/dev/null || true
      if ! git fetch "wt-$TID" 2>/dev/null; then
        echo "[escalation:git:merge_conflict] fetch failed for parent $key ($TID)" >&2
        exit 2
      fi
      cd "$WS"
      if ! git merge "wt-$TID/$PB" --no-edit 2>/dev/null; then
        echo "[escalation:git:merge_conflict] merge failed for parent $key ($TID)" >&2
        git diff --name-only --diff-filter=U 2>/dev/null || true
        exit 2
      fi
      cd "$REPO_ROOT"
      git remote remove "wt-$TID" 2>/dev/null || true
    done
    echo "OK integrated parents into $WS"
    ;;
  restore-plan)
    PLAN_ID=""
    WORKTREE=""
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
        --worktree) WORKTREE="${2:-}"; shift 2 ;;
        --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ -z "$PLAN_ID" || -z "$WORKTREE" ]] && { echo "usage: restore-plan --plan-id ID --worktree PATH" >&2; exit 2; }
    _load_branch_config "$REPO_ROOT" || exit 1
    PLAN_REL="$(resolve_plan_file "$REPO_ROOT" "$PLAN_ID" "" 2>/dev/null || true)"
    [[ -z "$PLAN_REL" ]] && { echo "plan file not found for $PLAN_ID" >&2; exit 1; }
    git -C "$WORKTREE" fetch origin "$WORKING_BRANCH" 2>/dev/null || true
    git -C "$WORKTREE" checkout "origin/$WORKING_BRANCH" -- "$PLAN_REL" 2>/dev/null || \
      git -C "$WORKTREE" checkout "$WORKING_BRANCH" -- "$PLAN_REL"
    echo "OK restored $PLAN_REL into $WORKTREE"
    ;;
  freshness)
    WORKTREE=""
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --worktree) WORKTREE="${2:-}"; shift 2 ;;
        --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ -z "$WORKTREE" ]] && { echo "usage: freshness --worktree PATH" >&2; exit 2; }
    _load_branch_config "$REPO_ROOT" || exit 1
    git -C "$WORKTREE" fetch origin "$WORKING_BRANCH" 2>/dev/null || true
    BEHIND="$(git -C "$WORKTREE" rev-list --count "HEAD..origin/$WORKING_BRANCH" 2>/dev/null || echo 0)"
    ACTION="none"
    [[ "${BEHIND:-0}" -gt 0 ]] && ACTION="merge"
    printf '{"behind_integration":%s,"action":"%s"}\n' "${BEHIND:-0}" "$ACTION"
    ;;
  audit)
    bash "$SCRIPT_DIR/git_safe_cleanup.sh" --audit
    ;;
  *)
    echo "unknown subcommand: $CMD" >&2
    exit 2
    ;;
esac
