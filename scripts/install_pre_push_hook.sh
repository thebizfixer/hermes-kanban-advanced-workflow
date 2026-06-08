#!/usr/bin/env bash
# install_pre_push_hook.sh — Install pre-push hook in a kanban worktree.
#
# Usage:
#   bash install_pre_push_hook.sh <worktree_path> <allowed_branch_pattern> <working_branch> <trigger_branch>
#
# All four arguments are required — no defaults.
set -euo pipefail

WORKTREE_PATH="${1:?worktree_path required}"
ALLOWED_PATTERN="${2:?allowed_branch_pattern required}"
WORKING_BRANCH="${3:?working_branch required}"
TRIGGER_BRANCH="${4:?trigger_branch required}"

if [ ! -d "$WORKTREE_PATH" ]; then
    echo "[kanban-governance] ERROR: worktree path does not exist: $WORKTREE_PATH" >&2
    exit 1
fi

GIT_DIR=$(git -C "$WORKTREE_PATH" rev-parse --git-dir 2>/dev/null)
if [ -z "$GIT_DIR" ]; then
    echo "[kanban-governance] ERROR: not a git worktree: $WORKTREE_PATH" >&2
    exit 1
fi

# Worktrees use a .git file pointing at the main repo's worktrees/<name>/ directory.
case "$GIT_DIR" in
    /*|./*|../*|[A-Za-z]:*)
        HOOKS_DIR="$GIT_DIR/hooks"
        ;;
    *)
        HOOKS_DIR="$(git -C "$WORKTREE_PATH" rev-parse --absolute-git-dir)/hooks"
        ;;
esac

mkdir -p "$HOOKS_DIR"

HOOK_FILE="$HOOKS_DIR/pre-push"
cat > "$HOOK_FILE" <<EOF
#!/usr/bin/env bash
# Installed by kanban-advanced worktree_setup.sh — do not edit manually.
# Branch names are read from kanban-config.yaml at install time, not hardcoded here.
ALLOWED_PATTERN="${ALLOWED_PATTERN}"
WORKING_BRANCH="${WORKING_BRANCH}"
TRIGGER_BRANCH="${TRIGGER_BRANCH}"

while read -r local_ref local_sha remote_ref remote_sha; do
    [ -z "\${remote_ref:-}" ] && continue
    branch="\${remote_ref#refs/heads/}"
    if [[ "\$branch" != \$ALLOWED_PATTERN ]]; then
        echo "[kanban-governance] BLOCKED: push to '\$branch' is not allowed from this worktree."
        echo "[kanban-governance] Allowed branch:   \$ALLOWED_PATTERN"
        echo "[kanban-governance] Protected:        \$WORKING_BRANCH, \$TRIGGER_BRANCH"
        echo "[kanban-governance] Commit to your worktree branch; the worker/orchestrator handles merge."
        exit 1
    fi
done
exit 0
EOF

chmod +x "$HOOK_FILE"
echo "[kanban-governance] pre-push hook installed at $HOOK_FILE"
