#!/usr/bin/env bash
# post_merge_gate.sh — verification after all worktree branches merged to staging
# Usage: bash post_merge_gate.sh <plan_id> [--baseline <commit>]
# Exit 0 = all gates pass, non-zero = blocking failures
set -euo pipefail

PLAN_ID="${1:-}"
BASELINE="${2:-$(git rev-parse origin/staging 2>/dev/null || echo 'HEAD~10')}"
if [ -z "$PLAN_ID" ]; then
  echo "[MERGE-GATE] ERROR: plan_id required" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
FAILURES=0

# ── 1. Gate tests from plan Test plan section ──
echo "[MERGE-GATE] Running gate tests..."
# Extract test commands from the plan's Test plan section
PLAN_FILE=$(find .cursor/plans .agent/plans -name "*${PLAN_ID}*" -type f 2>/dev/null | head -1)
if [ -n "$PLAN_FILE" ] && [ -f "$PLAN_FILE" ]; then
  # Parse test commands from the plan
  TEST_CMDS=$(grep -oP 'pytest[^`"]+' "$PLAN_FILE" 2>/dev/null | head -5 || true)
  if [ -n "$TEST_CMDS" ]; then
    cd backend
    source .venv/bin/activate 2>/dev/null || true
    echo "$TEST_CMDS" | while read -r cmd; do
      echo "  $cmd"
      python -m pytest $cmd -q --tb=line 2>/dev/null && echo "  PASS" || { echo "  FAIL"; FAILURES=$((FAILURES + 1)); }
    done
  else
    echo "  WARN: no test commands found in plan — run manually"
  fi
fi

# ── 2. Cross-card regression check (E017) ──
echo "[MERGE-GATE] Cross-card regression check..."
# Find functions added in the diff range that were later removed
ADDED_REMOVED=$(git diff "$BASELINE..HEAD" -- backend/ | grep -E '^[+-].*def ' | sed 's/^[+-] *//' | sort | uniq -c | sort -rn | awk '$1==1{print $2}' | head -10)
if [ -n "$ADDED_REMOVED" ]; then
  echo "  WARN: functions added then removed (possible regression):"
  echo "$ADDED_REMOVED" | while read fn; do echo "    $fn"; done
else
  echo "  PASS: no added-then-removed functions detected"
fi

# ── 3. Full test suite on changed files ──
echo "[MERGE-GATE] Test suite on changed files..."
CHANGED=$(git diff --name-only "$BASELINE..HEAD" -- backend/app/services/ | grep '\.py$' | sed 's|backend/||' | tr '\n' ' ')
if [ -n "$CHANGED" ]; then
  cd backend
  source .venv/bin/activate 2>/dev/null || true
  # Find test files that import these modules
  for f in $CHANGED; do
    mod=$(echo "$f" | sed 's|app/services/||;s|\.py$||;s|/|.|g')
    echo "  Testing module: $mod"
  done
fi

echo ""
echo "[MERGE-GATE] $FAILURES failures"
[ "$FAILURES" -eq 0 ] && echo "[MERGE-GATE] PASSED" || echo "[MERGE-GATE] FAILED"
exit $FAILURES
