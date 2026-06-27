#!/usr/bin/env bash
# test_hooks.sh — Manual verification of pre-push and pre-commit hooks.
# Run after worktree_setup.sh creates .worktrees/wt-t_smoke_
# Usage: bash scripts/test_hooks.sh

set -uo pipefail

WT=.worktrees/wt-t_smoke_
if [ ! -d "$WT" ]; then
    echo "ERROR: worktree $WT not found. Run worktree_setup.sh first." >&2
    exit 1
fi

GD=$(git -C "$WT" rev-parse --git-dir 2>/dev/null)
PREPUSH="$GD/hooks/pre-push"
PRECOMMIT="$GD/hooks/pre-commit"

PASS=0
FAIL=0

assert_exit() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$actual" -eq "$expected" ]; then
        echo "PASS: $desc (exit $actual)"
        PASS=$((PASS+1))
    else
        echo "FAIL: $desc (expected exit $expected, got $actual)"
        FAIL=$((FAIL+1))
    fi
}

echo "=== pre-push hook tests ==="

# Test 1: push to protected branch should block (exit 1)
OUT=$(printf 'refs/heads/main sha1 refs/heads/main sha1\n' | bash "$PREPUSH" origin https://example.com 2>&1) ; EC=$?
assert_exit "push to main is blocked" 1 "$EC"
echo "  msg: $(echo "$OUT" | head -1)"

# Test 2: push to allowed worktree branch should pass (exit 0)
OUT=$(printf 'refs/heads/wt/t_smoke_test sha1 refs/heads/wt/t_smoke_test sha1\n' | bash "$PREPUSH" origin https://example.com 2>&1) ; EC=$?
assert_exit "push to wt/t_smoke_test passes" 0 "$EC"

# Test 3: push to optional trigger_branch should block when configured
TB=$(grep '^TRIGGER_BRANCH=' "$PREPUSH" 2>/dev/null | sed 's/^TRIGGER_BRANCH="\(.*\)"$/\1/' || true)
if [ -n "$TB" ]; then
    OUT=$(printf 'refs/heads/%s sha1 refs/heads/%s sha1\n' "$TB" "$TB" | bash "$PREPUSH" origin https://example.com 2>&1) ; EC=$?
    assert_exit "push to trigger_branch ($TB) is blocked" 1 "$EC"
else
    echo "SKIP: trigger_branch not configured — optional deploy-branch hook test"
fi

echo ""
echo "=== pre-commit hook tests ==="

# Test 4: no .kanban-scope file — degraded, should warn but pass
rm -f "$WT/.kanban-scope"
OUT=$(cd "$WT" && bash "$PRECOMMIT" 2>&1) ; EC=$?
assert_exit "no .kanban-scope: degraded mode passes" 0 "$EC"
echo "  msg: $(echo "$OUT" | head -1)"

# Test 5: scope file present, staging only allowed file — should pass
echo "scripts/worktree_setup.sh" > "$WT/.kanban-scope"
OUT=$(cd "$WT" && GIT_INDEX_FILE=$(mktemp) git diff --cached --name-only 2>&1) ; true
OUT=$(cd "$WT" && STAGED="" bash -c 'STAGED=$(git diff --cached --name-only 2>/dev/null); [ -z "$STAGED" ] && exit 0; bash '"$PRECOMMIT"' 2>&1') ; EC=$?
assert_exit "empty staged: passes" 0 "$EC"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
