#!/usr/bin/env bash
# validate_board.sh â€” Pre-dispatch structural gate for kanban-advanced.
#
# Run BEFORE the orchestrator completes the gate card. Validates that the decomposition
# follows every governance rule. Exit 0 = pass, exit 1 = blocking failure.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/validate_board.sh
#   bash hermes-kanban-advanced-workflow/scripts/validate_board.sh --strict
#   bash hermes-kanban-advanced-workflow/scripts/validate_board.sh --profile advisory
#
# Profile resolution: --profile / --strict override, then KANBAN_POLICY_PROFILE,
# then kanban-config.yaml policy_profile (default: balanced).

set -euo pipefail
export LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI_PARSE="$SCRIPT_DIR/lib/cli_output_parse.py"

PROFILE_OVERRIDE=""
PLAN_ID=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --strict) PROFILE_OVERRIDE="strict"; shift ;;
        --profile) PROFILE_OVERRIDE="${2:-}"; shift 2 ;;
        --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
        *) shift ;;
    esac
done
FAILURES=0
WARNINGS=0
WORKER_PROFILE="${WORKER_PROFILE:-kanban-advanced-worker}"
ORCHESTRATOR_PROFILE="${ORCHESTRATOR_PROFILE:-kanban-advanced-orchestrator}"

# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

REPO_ROOT="$(resolve_project_root "$SCRIPT_DIR")"
# shellcheck source=lib/governance_profile.sh
source "$SCRIPT_DIR/lib/governance_profile.sh"
load_governance_profile "$REPO_ROOT" "$PROFILE_OVERRIDE"
echo "Governance profile: $GOVERNANCE_PROFILE"
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

fail() { red "  FAIL: $*"; FAILURES=$((FAILURES + 1)); }
warn() { yellow "  WARN: $*"; WARNINGS=$((WARNINGS + 1)); }
pass() { green "  âœ“ $*"; }

body_has_files() {
    echo "$1" | grep -qE '^(Files:|files:)'
}

body_has_tests() {
    echo "$1" | grep -qE '^(Tests:|tests:)'
}

body_tests_valid() {
    echo "$1" | PYTHONPATH="$SCRIPT_DIR/lib" python3 -c "
import sys
from card_body import body_tests_valid
sys.exit(0 if body_tests_valid(sys.stdin.read()) else 1)
"
}

body_is_verification_local() {
    echo "$1" | grep -qiE '^(Type:|type:)[[:space:]]*verification(-local)?[[:space:]]*$'
}

body_is_verification_deploy() {
    echo "$1" | grep -qiE '^(Type:|type:)[[:space:]]*verification-deploy[[:space:]]*$' \
        || echo "$1" | grep -qiE '^Deploy:'
}

body_is_verification() {
    body_is_verification_local "$1" || body_is_verification_deploy "$1"
}

echo "=== Pre-Dispatch Board Validation ==="
echo ""

# â”€â”€ 0. Cron health check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "0. Cron health check"
CRON_ISSUES=0
# Source hermes_home.sh for $HERMES_HOME (cron scripts resolve there)
SCRIPT_DIR_VAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR_VAL/lib/hermes_home.sh"

CRON_SCRIPTS_DIR="${HERMES_HOME}/scripts"
# Windows crons use .py launchers (hermes #23404 workaround); Unix uses .sh directly
if [[ "$OS" == *"Windows"* || "$(uname -s 2>/dev/null)" == MINGW* || "$(uname -s 2>/dev/null)" == MSYS* ]]; then
    CRON_SCRIPT_PAIRS="auto_unblock.py board_keeper.py"
else
    CRON_SCRIPT_PAIRS="auto_unblock.sh board_keeper.sh"
fi
ALL_PRESENT=true
ALL_EXEC=true
for s in $CRON_SCRIPT_PAIRS; do
    if [ -f "${CRON_SCRIPTS_DIR}/$s" ]; then
        if [ -x "${CRON_SCRIPTS_DIR}/$s" ]; then
            :  # present and executable
        else
            fail "Cron script ${CRON_SCRIPTS_DIR}/$s exists but is NOT executable â€” cron will fail silently"
            ALL_EXEC=false
            CRON_ISSUES=$((CRON_ISSUES + 1))
        fi
    else
        fail "Cron script ${CRON_SCRIPTS_DIR}/$s missing â€” run provision.sh to sync"
        ALL_PRESENT=false
        CRON_ISSUES=$((CRON_ISSUES + 1))
    fi
done
$ALL_PRESENT && $ALL_EXEC && pass "Cron scripts present and executable at ${CRON_SCRIPTS_DIR}/"

# Verify hermes is on PATH (cron environment may differ from interactive shell)
if command -v hermes >/dev/null 2>&1; then
    pass "hermes on PATH â€” cron scripts can invoke kanban commands"
else
    # Check common install locations
    FOUND_HERMES=""
    for candidate in "$HOME/.local/bin/hermes" "$HOME/.nix-profile/bin/hermes" "/usr/local/bin/hermes"; do
        [ -x "$candidate" ] && FOUND_HERMES="$candidate" && break
    done
    if [ -n "$FOUND_HERMES" ]; then
        warn "hermes found at $FOUND_HERMES but not on default PATH â€” cron may need explicit PATH setup"
    else
        fail "hermes not found on PATH or common locations â€” cron scripts will fail"
        CRON_ISSUES=$((CRON_ISSUES + 1))
    fi
fi

# Verify per-plan wave crons (provision script — deliver=local, no-agent, active)
if command -v hermes >/dev/null 2>&1; then
    if bash "$SCRIPT_DIR_VAL/provision_kanban_crons.sh" --check 2>/dev/null; then
        pass "wave crons active (auto_unblock + board_keeper, deliver=local)"
    else
        fail "wave crons check failed — run kanban_handoff.py (default profile) or provision_kanban_crons.sh --create --check before decomposition"
        CRON_ISSUES=$((CRON_ISSUES + 1))
    fi
else
    warn "hermes CLI not available â€” cannot verify crons are running"
fi

# â”€â”€ 1. No card uses --parents flag â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "1. --parents flag check (P008)"
# Check for cards created with --parents by looking for cards with 
# empty parents list but body that mentions dependency expectations.
# In practice: run hermes kanban show on each card, check if parents
# were specified at creation vs added later via link.
PARENTLESS_CARDS=$(hermes kanban list 2>/dev/null | awk '/â–¶|â—|â—»|âŠ˜/ {print $2}')
PARENT_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    # Check if body mentions "Depends on" but no parents in metadata
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    if echo "$BODY" | grep -q "Depends on\|depends on" && echo "$BODY" | grep -q "parents:.*-"; then
        : # Has deps mentioned AND parents listed â€” OK
    elif echo "$BODY" | grep -q "Depends on\|depends on"; then
        fail "Card $tid mentions dependencies but has no parent links â€” was --parents used?"
        PARENT_ISSUES=$((PARENT_ISSUES + 1))
    fi
done
[ $PARENT_ISSUES -eq 0 ] && pass "No orphaned dependency declarations"

# â”€â”€ 2. No code-gen card has scratch workspace â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "2. Scratch workspace check (P006)"
SCRATCH_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1)
    if echo "$WS" | grep -q "scratch"; then
        BODY=$(hermes kanban show "$tid" 2>/dev/null)
        if body_has_files "$BODY"; then
            fail "Code-gen card $tid has scratch workspace (zero output risk)"
            SCRATCH_ISSUES=$((SCRATCH_ISSUES + 1))
        fi
    fi
done
[ $SCRATCH_ISSUES -eq 0 ] && pass "No code-gen scratch workspaces"

# â”€â”€ 3. No shared workspace paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "3. Shared workspace check (P007)"
declare -A WORKSPACES
SHARED_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1 | sed 's/.*@ //' | xargs)
    [ -z "$WS" ] && continue
    if [[ -n "${WORKSPACES[$WS]:-}" ]]; then
        fail "Shared workspace: $tid and ${WORKSPACES[$WS]} both use $WS"
        SHARED_ISSUES=$((SHARED_ISSUES + 1))
    else
        WORKSPACES[$WS]="$tid"
    fi
done
[ $SHARED_ISSUES -eq 0 ] && pass "All workspaces unique"

# â”€â”€ 4. All dependent cards have parent links â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "4. Parent link verification"
LINK_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    PARENTS=$(echo "$BODY" | grep "parents:" | head -1)
    if echo "$BODY" | grep -q "Depends on\|depends on" && echo "$PARENTS" | grep -q "parents:.*-"; then
        : # Has deps AND parents â€” OK
    elif echo "$BODY" | grep -q "Depends on\|depends on"; then
        fail "Card $tid has stated dependencies but no parent links established"
        LINK_ISSUES=$((LINK_ISSUES + 1))
    fi
done
[ $LINK_ISSUES -eq 0 ] && pass "All dependency links established"

# â”€â”€ 5. Dependent cards not dispatched before parents done â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "5. Parent completion check"
PENDING_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    STATUS=$(hermes kanban show "$tid" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}')
    [[ "$STATUS" == "done" ]] && continue
    PARENTS=$(hermes kanban show "$tid" 2>/dev/null | python3 "$CLI_PARSE" parents 2>/dev/null || true)
    for parent in $PARENTS; do
        PSTATUS=$(hermes kanban show "$parent" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}')
        if [[ "$PSTATUS" != "done" ]]; then
            if [[ "$STATUS" == "running" || "$STATUS" == "ready" ]]; then
                fail "Card $tid is $STATUS but parent $parent is $PSTATUS (not done)"
                PENDING_ISSUES=$((PENDING_ISSUES + 1))
            fi
        fi
    done
done
[ $PENDING_ISSUES -eq 0 ] && pass "No cards running before parents complete"

# â”€â”€ 6. No more than ~10 functions per extraction card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "6. Iteration budget heuristic (P009)"
BUDGET_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    FN_COUNT=$(echo "$BODY" | grep -c 'def \|async def \|class ' || true)
    if [ "$FN_COUNT" -gt 10 ]; then
        warn "Card $tid mentions ~$FN_COUNT functions/classes (>10) â€” may exceed 35-turn budget"
        BUDGET_ISSUES=$((BUDGET_ISSUES + 1))
    fi
done
[ $BUDGET_ISSUES -eq 0 ] && pass "No cards exceed function-count heuristic"
[ $BUDGET_ISSUES -gt 0 ] && warn "$BUDGET_ISSUES card(s) exceed 10-function heuristic â€” review for splitting"

# â”€â”€ 7. Max-retries enforcement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "7. Max-retries â‰¤2 (mandatory)"
RETRY_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    MAX_RETRIES=$(hermes kanban show "$tid" 2>/dev/null | python3 "$CLI_PARSE" max-retries 2>/dev/null || echo "0")
    if [ "$MAX_RETRIES" -gt 2 ] 2>/dev/null || [ "$MAX_RETRIES" -eq 0 ] 2>/dev/null; then
        CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
        if governance_warnings_block; then
            fail "Card $tid ($CARD_NAME) has max-retries=$MAX_RETRIES (must be â‰¤2)"
        else
            warn "Card $tid ($CARD_NAME) has max-retries=$MAX_RETRIES (should be â‰¤2)"
        fi
        RETRY_ISSUES=$((RETRY_ISSUES + 1))
    fi
done
[ $RETRY_ISSUES -eq 0 ] && pass "All cards have max-retries â‰¤2"

# â”€â”€ 8. Orphaned agent processes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "8. Orphaned agent check"
ORPHANS=$(ps aux | grep 'kanban task t_' | grep -v grep | awk '{print $NF}' | python3 "$CLI_PARSE" task-ids 2>/dev/null | sort -u || true)
ORPHAN_ISSUES=0
for tid in $ORPHANS; do
    if ! hermes kanban show "$tid" &>/dev/null; then
        warn "Orphaned agent process for archived/deleted card $tid"
        ORPHAN_ISSUES=$((ORPHAN_ISSUES + 1))
    fi
done
[ $ORPHAN_ISSUES -eq 0 ] && pass "No orphaned agent processes"

# â”€â”€ 9. Worker-assigned cards must have agent -p blocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "9. Agent block presence (P002 â€” protocol violation prevention)"
AGENT_BLOCK_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_FILES=0
    body_has_files "$BODY" && HAS_FILES=1
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_FILES" -gt 0 ] && [ "$HAS_AGENT" -eq 0 ] && ! body_is_verification "$BODY"; then
        fail "Card $tid (assignee=$ASSIGNEE) has Files: but no agent -p block â€” will protocol-violate"
        AGENT_BLOCK_ISSUES=$((AGENT_BLOCK_ISSUES + 1))
    fi
done
[ $AGENT_BLOCK_ISSUES -eq 0 ] && pass "All worker cards have agent -p blocks"

# â”€â”€ 10. Orchestrator-only cards must NOT block worker dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "10. Orchestrator-only card assignment"
ORCH_ONLY_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    # Gate and audit cards have no agent block â€” they're manual orchestrator steps
    TITLE=$(echo "$BODY" | grep "Task $tid:" | head -1)
    IS_VERIFICATION=0
    body_is_verification "$BODY" && IS_VERIFICATION=1
    HAS_FILES=0
    body_has_files "$BODY" && HAS_FILES=1
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && body_is_verification_deploy "$BODY"; then
        fail "Card $tid (assignee=$ASSIGNEE) Type: verification-deploy must use orchestrator profile"
        ORCH_ONLY_ISSUES=$((ORCH_ONLY_ISSUES + 1))
    elif [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$IS_VERIFICATION" -gt 0 ] && [ "$HAS_FILES" -gt 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) Type: verification must not have Files: line"
        ORCH_ONLY_ISSUES=$((ORCH_ONLY_ISSUES + 1))
    elif [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$IS_VERIFICATION" -gt 0 ] && [ "$HAS_AGENT" -gt 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) Type: verification must not have agent block"
        ORCH_ONLY_ISSUES=$((ORCH_ONLY_ISSUES + 1))
    elif [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_AGENT" -eq 0 ] && echo "$TITLE" | grep -qiE 'gate|audit|root'; then
        fail "Card $tid (assignee=$ASSIGNEE) is an orchestrator-only card (gate/audit/root) but assigned to worker profile â€” will protocol-violate"
        ORCH_ONLY_ISSUES=$((ORCH_ONLY_ISSUES + 1))
    fi
done
[ $ORCH_ONLY_ISSUES -eq 0 ] && pass "No orchestrator-only cards assigned to workers"

# ── 11. Worker cards must have Tests: line ─────────────────────────────
echo "11. Tests: line presence and syntax (E003 / P014 prevention)"
TEST_LINE_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    HAS_TESTS=0
    body_has_tests "$BODY" && HAS_TESTS=1
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    IS_VERIFICATION=0
    body_is_verification "$BODY" && IS_VERIFICATION=1
    if [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$IS_VERIFICATION" -gt 0 ] && [ "$HAS_TESTS" -eq 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) Type: verification requires Tests: line"
        TEST_LINE_ISSUES=$((TEST_LINE_ISSUES + 1))
    elif [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_AGENT" -gt 0 ] && [ "$HAS_TESTS" -eq 0 ]; then
        fail "Card $tid (assignee=$ASSIGNEE) has agent block but no Tests: line — evaluation chain will silently pass"
        TEST_LINE_ISSUES=$((TEST_LINE_ISSUES + 1))
    elif [[ "$ASSIGNEE" == "$WORKER_PROFILE" ]] && [ "$HAS_TESTS" -gt 0 ] && ! body_tests_valid "$BODY"; then
        fail "Card $tid (assignee=$ASSIGNEE) Tests: line is malformed — fix shell syntax or move prose to Acceptance:"
        TEST_LINE_ISSUES=$((TEST_LINE_ISSUES + 1))
    fi
done
[ $TEST_LINE_ISSUES -eq 0 ] && pass "All worker cards have valid Tests: line"

# ── 12. Card self-sufficiency (completeness-loop readiness) ────────────
echo "12. Card self-sufficiency (plan_id, Acceptance, Call-sites, Parent-branches)"
SELF_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    echo "$BODY" | grep -qi 'Type: remediation' && continue
    echo "$BODY" | grep -qi 'Type: orchestrator-handoff' && continue
    body_is_verification "$BODY" && continue
    HAS_AGENT=$(echo "$BODY" | grep -c '```agent' || true)
    [ "$HAS_AGENT" -eq 0 ] && continue
    ASSIGNEE=$(echo "$BODY" | grep "assignee:" | head -1 | awk '{print $2}')
    [[ "$ASSIGNEE" != "$WORKER_PROFILE" ]] && continue
    echo "$BODY" | grep -qiE '^plan_id:\s*\S+' || { fail "Card $tid missing plan_id:"; SELF_ISSUES=$((SELF_ISSUES + 1)); }
    echo "$BODY" | grep -q 'Acceptance:' || { fail "Card $tid missing Acceptance:"; SELF_ISSUES=$((SELF_ISSUES + 1)); }
    FILE_COUNT=$(echo "$BODY" | grep -E '^Files:' | head -1 | tr ',' '\n' | grep -c '.' || true)
    if [ "${FILE_COUNT:-0}" -ge 2 ] && ! echo "$BODY" | grep -q 'Call-sites:'; then
        fail "Card $tid has 2+ files but no Call-sites:"
        SELF_ISSUES=$((SELF_ISSUES + 1))
    fi
    if echo "$BODY" | grep -qiE '^parents:\s*\S+' && ! echo "$BODY" | grep -q 'Parent-branches:'; then
        fail "Card $tid has parents: metadata but no Parent-branches:"
        SELF_ISSUES=$((SELF_ISSUES + 1))
    fi
done
[ $SELF_ISSUES -eq 0 ] && pass "Worker cards self-sufficient for completeness loop"

# -- 13. Audit card remediation children (final audit phase) -----------------
echo "13. Audit remediation children (mandatory for Type: audit)"
CHECK13_ISSUES=0
for tid in $PARENTLESS_CARDS; do
    BODY=$(hermes kanban show "$tid" 2>/dev/null)
    echo "$BODY" | grep -qiE 'Type:[[:space:]]*audit' || continue
    STATUS=$(echo "$BODY" | grep "status:" | head -1 | awk '{print $2}')
    [[ "$STATUS" != "done" ]] && continue
    REMEDIATION_CHILDREN=""
    REMEDIATION_CHILDREN="$(hermes kanban list --parent "$tid" 2>/dev/null | awk '/^t_/ {print $1}' || true)"
    USED_PARENT_LIST=false
    if [[ -n "$REMEDIATION_CHILDREN" ]]; then
        USED_PARENT_LIST=true
    else
        REMEDIATION_CHILDREN="$(hermes kanban list 2>/dev/null | awk '/^t_/ {print $1}' || true)"
    fi
    for cid in $REMEDIATION_CHILDREN; do
        CDETAIL=$(hermes kanban show "$cid" 2>/dev/null)
        [[ -z "$CDETAIL" ]] && continue
        echo "$CDETAIL" | grep -qiE 'Type:[[:space:]]*remediation' || continue
        if [[ "$USED_PARENT_LIST" != true ]]; then
            echo "$CDETAIL" | grep -q "$tid" || continue
        fi
        CSTATUS=$(echo "$CDETAIL" | grep "status:" | head -1 | awk '{print $2}')
        if [[ "$CSTATUS" != "done" && "$CSTATUS" != "archived" ]]; then
            fail "[FAIL check13] Audit card $tid has open remediation child $cid (status=$CSTATUS)"
            CHECK13_ISSUES=$((CHECK13_ISSUES + 1))
        fi
    done
done
[ $CHECK13_ISSUES -eq 0 ] && pass "No done audit cards with open remediation children"

echo ""
echo "=== Results: $FAILURES failures, $WARNINGS warnings ==="

if [ "$FAILURES" -gt 0 ] && governance_failures_block; then
    red "BLOCKED: $FAILURES structural violation(s). Fix before completing gate."
    exit 1
elif [ "$FAILURES" -gt 0 ]; then
    yellow "PASS (advisory): $FAILURES failure(s) downgraded to warnings."
    exit 0
elif [ "$WARNINGS" -gt 0 ] && governance_warnings_block; then
    yellow "BLOCKED (strict profile): $WARNINGS warning(s) treated as blocking."
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    yellow "PASS with $WARNINGS warning(s). Review before proceeding."
    exit 0
else
    green "PASS: All structural checks passed. Safe to complete gate."
    exit 0
fi
