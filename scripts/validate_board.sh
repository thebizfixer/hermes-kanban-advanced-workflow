#!/usr/bin/env bash
# validate_board.sh — Pre-dispatch structural gate for kanban-advanced.
#
# Run BEFORE unblocking the gate card. Validates that the decomposition
# follows every governance rule. Exit 0 = pass, exit 1 = blocking failure.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/validate_board.sh
#   bash hermes-kanban-advanced-workflow/scripts/validate_board.sh --strict

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-balanced}"  # balanced | strict
FAILURES=0
WARNINGS=0
WORKER_PROFILE="${WORKER_PROFILE:-code-worker}"
ORCHESTRATOR_PROFILE="${ORCHESTRATOR_PROFILE:-orchestrator}"

find_repo_root() {
  local dir="$SCRIPT_DIR"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/.env" || -d "$dir/.git" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  printf '%s\n' "$BUNDLE_DIR"
}

REPO_ROOT="$(find_repo_root)"
OVERLAY_CONFIG="$REPO_ROOT/.hermes/kanban-overrides/kanban-config.yaml"
if [[ -f "$OVERLAY_CONFIG" ]]; then
  _wp="$(grep -E '^worker_profile:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^worker_profile: *//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')"
  [[ -n "$_wp" ]] && WORKER_PROFILE="$_wp"
  _op="$(grep -E '^orchestrator_profile:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^orchestrator_profile: *//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')"
  [[ -n "$_op" ]] && ORCHESTRATOR_PROFILE="$_op"
fi

red()  { echo -e "\033[31m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
green() { echo -e "\033[32m$*\033[0m"; }

fail() { red "  ✗ FAIL: $*"; ((FAILURES++)); }
warn() { yellow "  ⚠ WARN: $*"; ((WARNINGS++)); }
pass() { green "  ✓ $*"; }

echo "=== Pre-Dispatch Board Validation ==="
echo ""

# ── 0. Cron health check ───────────────────────────────────────────────
echo "0. Cron health check"
CRON_ISSUES=0
# Source hermes_home.sh for $HERMES_HOME (cron scripts resolve there)
SCRIPT_DIR_VAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR_VAL/lib/hermes_home.sh"

CRON_SCRIPTS_DIR="${HERMES_HOME}/scripts"
CRON_SCRIPT_PAIRS="auto_unblock.sh board_keeper.sh"
ALL_PRESENT=true
ALL_EXEC=true
for s in $CRON_SCRIPT_PAIRS; do
    if [ -f "${CRON_SCRIPTS_DIR}/$s" ]; then
        if [ -x "${CRON_SCRIPTS_DIR}/$s" ]; then
            :  # present and executable
        else
            fail "Cron script ${CRON_SCRIPTS_DIR}/$s exists but is NOT executable — cron will fail silently"
            ALL_EXEC=false
            ((CRON_ISSUES++))
        fi
    else
        fail "Cron script ${CRON_SCRIPTS_DIR}/$s missing — run provision.sh to sync"
        ALL_PRESENT=false
        ((CRON_ISSUES++))
    fi
done
$ALL_PRESENT && $ALL_EXEC && pass "Cron scripts present and executable at ${CRON_SCRIPTS_DIR}/"

# Verify hermes is on PATH (cron environment may differ from interactive shell)
if command -v hermes >/dev/null 2>&1; then
    pass "hermes on PATH — cron scripts can invoke kanban commands"
else
    # Check common install locations
    FOUND_HERMES=""
    for candidate in "$HOME/.local/bin/hermes" "$HOME/.nix-profile/bin/hermes" "/usr/local/bin/hermes"; do
        [ -x "$candidate" ] && FOUND_HERMES="$candidate" && break
    done
    if [ -n "$FOUND_HERMES" ]; then
        warn "hermes found at $FOUND_HERMES but not on default PATH — cron may need explicit PATH setup"
    else
        fail "hermes not found on PATH or common locations — cron scripts will fail"
        ((CRON_ISSUES++))
    fi
fi

# Check cron jobs exist via cronjob CLI (non-blocking if CLI unavailable)
if command -v hermes >/dev/null 2>&1; then
    CRON_LIST=$(hermes cron list 2>/dev/null || true)
    for expected in "auto_unblock" "board_keeper"; do
        if echo "$CRON_LIST" | grep -q "$expected"; then
            pass "$expected cron found and running"
        else
            fail "$expected cron NOT found — gate cannot be unblocked until cron is created"
            ((CRON_ISSUES++))
        fi
    done
else
    warn "hermes CLI not available — cannot verify crons are running"
fi

# ── 1. No card uses --parents flag ──────────────────────────────────────
echo "1. --parents flag check (P008)"
# Check for cards created with --parents by looking for cards with 
# empty parents list but body that mentions dependency expectations.
# In practice: run hermes kanban show on each card, check if parents
# were specified at creation vs added later via link.
PARENTLESS_CARDS=$(hermes kanban list 2>/dev/null | awk '/▶|●|◻|⊘/ {print $2}')
PARENT_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    # Check if body mentions "Depends on" but no parents in metadata
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    if echo "$BODY" | grep -q "Depends on\|depends on" && echo "$BODY" | grep -q "parents:.*-"; then
        : # Has deps mentioned AND parents listed — OK
    elif echo "$BODY" | grep -q "Depends on\|depends on"; then
        fail "Card $tid mentions dependencies but has no parent links — was --parents used?"
        ((PARENT_ISSUES++))
    fi
done
[ $PARENT_ISSUES -eq 0 ] && pass "No orphaned dependency declarations"

# ── 2. No code-gen card has scratch workspace ───────────────────────────
echo "2. Scratch workspace check (P006)"
SCRATCH_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1)
    if echo "$WS" | grep -q "scratch"; then
        BODY=$(hermes kanban show "$tid" 2>/dev/null)
        if echo "$BODY" | grep -q "Files:"; then
            fail "Code-gen card $tid has scratch workspace (zero output risk)"
            ((SCRATCH_ISSUES++))
        fi
    fi
done
[ $SCRATCH_ISSUES -eq 0 ] && pass "No code-gen scratch workspaces"

# ── 3. No shared workspace paths ────────────────────────────────────────
echo "3. Shared workspace check (P007)"
declare -A WORKSPACES
SHARED_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1 | sed 's/.*@ //' | xargs)
    [ -z "$WS" ] && continue
    if [[ -n "${WORKSPACES[$WS]:-}" ]]; then
        fail "Shared workspace: $tid and ${WORKSPACES[$WS]} both use $WS"
        ((SHARED_ISSUES++))
    else
        WORKSPACES[$WS]="$tid"
    fi
done
[ $SHARED_ISSUES -eq 0 ] && pass "All workspaces unique"

# ── 4. All dependent cards have parent links ────────────────────────────
echo "4. Parent link verification"
LINK_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    PARENTS=$(echo "$BODY" | grep "parents:" | head -1)
    if echo "$BODY" | grep -q "Depends on\|depends on" && echo "$PARENTS" | grep -q "parents:.*-"; then
        : # Has deps AND parents — OK
    elif echo "$BODY" | grep -q "Depends on\|depends on"; then
        fail "Card $tid has stated dependencies but no parent links established"
        ((LINK_ISSUES++))
    fi
done
[ $LINK_ISSUES -eq 0 ] && pass "All dependency links established"

# ── 5. Dependent cards not dispatched before parents done ────────────────
echo "5. Parent completion check"
PENDING_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    STATUS=$(hermes kanban show "$tid" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}')
    [[ "$STATUS" == "done" ]] && continue
    PARENTS=$(hermes kanban show "$tid" 2>/dev/null | grep "parents:" | head -1 | grep -oP 't_\w+' || true)
    for parent in $PARENTS; do
        PSTATUS=$(hermes kanban show "$parent" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}')
        if [[ "$PSTATUS" != "done" ]]; then
            if [[ "$STATUS" == "running" || "$STATUS" == "ready" ]]; then
                fail "Card $tid is $STATUS but parent $parent is $PSTATUS (not done)"
                ((PENDING_ISSUES++))
            fi
        fi
    done
done
[ $PENDING_ISSUES -eq 0 ] && pass "No cards running before parents complete"

# ── 6. No more than ~10 functions per extraction card ─────────────────────
echo "6. Iteration budget heuristic (P009)"
BUDGET_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    FN_COUNT=$(echo "$BODY" | grep -c 'def \|async def \|class ' || true)
    if [ "$FN_COUNT" -gt 10 ]; then
        warn "Card $tid mentions ~$FN_COUNT functions/classes (>10) — may exceed 35-turn budget"
        ((BUDGET_ISSUES++))
    fi
done
[ $BUDGET_ISSUES -eq 0 ] && pass "No cards exceed function-count heuristic"
[ $BUDGET_ISSUES -gt 0 ] && warn "$BUDGET_ISSUES card(s) exceed 10-function heuristic — review for splitting"

# ── 7. Max-retries enforcement ──────────────────────────────────────────
echo "7. Max-retries ≤2 (mandatory)"
RETRY_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    MAX_RETRIES=$(hermes kanban show "$tid" 2>/dev/null | grep "max-retries:" | head -1 | grep -oP '\d+' || echo "0")
    if [ "$MAX_RETRIES" -gt 2 ] 2>/dev/null || [ "$MAX_RETRIES" -eq 0 ] 2>/dev/null; then
        CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
        if [ "$MODE" == "strict" ]; then
            fail "Card $tid ($CARD_NAME) has max-retries=$MAX_RETRIES (must be ≤2)"
        else
            warn "Card $tid ($CARD_NAME) has max-retries=$MAX_RETRIES (should be ≤2)"
        fi
        ((RETRY_ISSUES++))
    fi
done
[ $RETRY_ISSUES -eq 0 ] && pass "All cards have max-retries ≤2"

# ── 8. Orphaned agent processes ─────────────────────────────────────────
echo "8. Orphaned agent check"
ORPHANS=$(ps aux | grep 'kanban task t_' | grep -v grep | awk '{print $NF}' | grep -oP 't_\w+' | sort -u || true)
ORPHAN_ISSUES=0
for tid in $ORPHANS; do
    if ! hermes kanban show "$tid" &>/dev/null; then
        warn "Orphaned agent process for archived/deleted card $tid"
        ((ORPHAN_ISSUES++))
    fi
done
[ $ORPHAN_ISSUES -eq 0 ] && pass "No orphaned agent processes"

# ── 9. Worker-assigned cards must have agent -p blocks ─────────────────
echo "9. Agent block presence (P002 — protocol violation prevention)"
AGENT_BLOCK_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_FILES=$(echo "$BODY" | grep -c "Files:" || true)
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_FILES" -gt 0 ] && [ "$HAS_AGENT" -eq 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) has Files: but no agent -p block — will protocol-violate"
        ((AGENT_BLOCK_ISSUES++))
    fi
done
[ $AGENT_BLOCK_ISSUES -eq 0 ] && pass "All worker cards have agent -p blocks"

# ── 10. Orchestrator-only cards must NOT block worker dispatch ──────────
echo "10. Orchestrator-only card assignment"
ORCH_ONLY_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    # Gate and audit cards have no agent block — they're manual orchestrator steps
    TITLE=$(echo "$BODY" | grep "Task $tid:" | head -1)
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_AGENT" -eq 0 ] && echo "$TITLE" | grep -qiE 'gate|audit|root'; then
        fail "Card $tid (assignee=$ASSIGNEE) is an orchestrator-only card (gate/audit/root) but assigned to worker profile — will protocol-violate"
        ((ORCH_ONLY_ISSUES++))
    fi
done
[ $ORCH_ONLY_ISSUES -eq 0 ] && pass "No orchestrator-only cards assigned to workers"

# ── 11. Worker cards must have Tests: line ────────────────────────────
echo "11. Tests: line presence (E003 prevention)"
TEST_LINE_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_TESTS=$(echo "$BODY" | grep -c "Tests:" || true)
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_AGENT" -gt 0 ] && [ "$HAS_TESTS" -eq 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) has agent block but no Tests: line — evaluation chain will silently pass"
        ((TEST_LINE_ISSUES++))
    fi
done
[ $TEST_LINE_ISSUES -eq 0 ] && pass "All worker cards have Tests: line"

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $FAILURES failures, $WARNINGS warnings ==="

if [ "$FAILURES" -gt 0 ]; then
    red "BLOCKED: $FAILURES structural violation(s). Fix before unblocking gate."
    exit 1
elif [ "$WARNINGS" -gt 0 ] && [ "$MODE" == "strict" ]; then
    yellow "BLOCKED (strict mode): $WARNINGS warning(s) treated as blocking."
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    yellow "PASS with $WARNINGS warning(s). Review before proceeding."
    exit 0
else
    green "PASS: All structural checks passed. Safe to unblock gate."
    exit 0
fi
