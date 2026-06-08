#!/usr/bin/env bash
# install_pre_commit_hook.sh — Install pre-commit hook enforcing Files: boundary.
#
# Usage:
#   bash install_pre_commit_hook.sh <worktree_path>
#
# The worker writes .kanban-scope to the worktree root before agent spawn.
# The hook reads it at commit time (not at install time).
set -euo pipefail

WORKTREE_PATH="${1:?worktree_path required}"

if [ ! -d "$WORKTREE_PATH" ]; then
    echo "[kanban-governance] ERROR: worktree path does not exist: $WORKTREE_PATH" >&2
    exit 1
fi

GIT_DIR=$(git -C "$WORKTREE_PATH" rev-parse --git-dir 2>/dev/null)
if [ -z "$GIT_DIR" ]; then
    echo "[kanban-governance] ERROR: not a git worktree: $WORKTREE_PATH" >&2
    exit 1
fi

case "$GIT_DIR" in
    /*|./*|../*|[A-Za-z]:*)
        HOOKS_DIR="$GIT_DIR/hooks"
        ;;
    *)
        HOOKS_DIR="$(git -C "$WORKTREE_PATH" rev-parse --absolute-git-dir)/hooks"
        ;;
esac

mkdir -p "$HOOKS_DIR"

HOOK_FILE="$HOOKS_DIR/pre-commit"
cat > "$HOOK_FILE" <<'EOF'
#!/usr/bin/env bash
# Installed by kanban-advanced worktree_setup.sh — do not edit manually.
SCOPE_FILE="$(git rev-parse --show-toplevel)/.kanban-scope"

if [ ! -f "$SCOPE_FILE" ]; then
    echo "[kanban-governance] WARNING: .kanban-scope not found — worker has not set up scope yet."
    echo "[kanban-governance] Commit allowed (degraded mode). Worker must write scope before agent spawn."
    exit 0
fi

mapfile -t ALLOWED < "$SCOPE_FILE"
STAGED=$(git diff --cached --name-only)

VIOLATIONS=()
while IFS= read -r file; do
    [ -z "$file" ] && continue
    MATCH=0
    for allowed in "${ALLOWED[@]}"; do
        [ -z "$allowed" ] && continue
        [ "$file" = "$allowed" ] && MATCH=1 && break
    done
    [ "$MATCH" -eq 0 ] && VIOLATIONS+=("$file")
done <<< "$STAGED"

if [ ${#VIOLATIONS[@]} -gt 0 ]; then
    echo "[kanban-governance] BLOCKED: commit includes files outside Files: scope:"
    for v in "${VIOLATIONS[@]}"; do echo "  - $v"; done
    echo "[kanban-governance] Allowed: $(tr '\n' ' ' < "$SCOPE_FILE")"
    echo "[kanban-governance] Use: git restore --staged <file> to unstage violations."
    exit 1
fi
exit 0
EOF

chmod +x "$HOOK_FILE"
echo "[kanban-governance] pre-commit hook installed at $HOOK_FILE"
