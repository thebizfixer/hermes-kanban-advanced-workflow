#!/usr/bin/env bash
# verify_optimization.sh — Pre-optimize gate for kanban plan decomposition.
#
# Verifies structural checklist items from the planning skill before the
# orchestrator can declare "plan optimized." Runs as a blocking structural gate.
#
# Current scope: 15 checks covering Harden items 1,5,7,9,11,12 and
# Optimize items 1,2,3,6,7,8,11,15,18 plus goal-card annotations and
# sequential Card N labeling in ## Kanban optimization.
#
# Usage:
#   bash verify_optimization.sh --plan <plan.md>
#   bash verify_optimization.sh --plan <plan.md> --strict    # WARN becomes FAIL
#
# Exit codes:
#   0 — All checks pass
#   1 — One or more checks failed
#   2 — Usage error

set -euo pipefail

PLAN=""
STRICT=false
PROFILE_OVERRIDE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANCHOR_SCRIPT="$SCRIPT_DIR/verify_anchors.py"
PLAN_PARSE="$SCRIPT_DIR/lib/plan_parse.py"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan) PLAN="$2"; shift 2 ;;
        --strict) STRICT=true; PROFILE_OVERRIDE="strict"; shift ;;
        --profile) PROFILE_OVERRIDE="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 2 ;;
    esac
done

if [[ -z "$PLAN" ]]; then
    echo "Usage: verify_optimization.sh --plan <plan.md> [--strict]" >&2
    exit 2
fi
if [[ ! -f "$PLAN" ]]; then
    echo "ERROR: Plan file not found: $PLAN" >&2
    exit 2
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/governance_profile.sh
source "$SCRIPT_DIR/lib/governance_profile.sh"
load_governance_profile "$REPO_ROOT" "$PROFILE_OVERRIDE"
if [ "$GOVERNANCE_PROFILE" = "strict" ]; then
    STRICT=true
fi
echo "Governance profile: $GOVERNANCE_PROFILE"
FAILURES=0
WARNINGS=0
PASSES=0
CHECKS_RUN=0

red()    { echo -e "\033[31m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }

check_pass() { green "  ✓ $*"; ((PASSES++)); ((CHECKS_RUN++)); }
check_warn() { yellow "  ⚠ WARN: $*"; ((WARNINGS++)); ((CHECKS_RUN++)); }
check_fail() {
    if governance_failures_block; then
        red "  ✗ FAIL: $*"
        ((FAILURES++))
    else
        yellow "  ⚠ ADVISORY: $*"
        ((WARNINGS++))
    fi
    ((CHECKS_RUN++))
}

echo "=== Plan Optimization Gate: $PLAN ==="
echo ""

PLAN_CONTENT=$(cat "$PLAN")
PLAN_DIR=$(dirname "$PLAN")

# ── 1. Anchor points verified ───────────────────────────────────────────
echo "1. Anchor points verified"
if [[ -x "$ANCHOR_SCRIPT" ]] || [[ -f "$ANCHOR_SCRIPT" ]]; then
    ANCHOR_OUTPUT=$(python3 "$ANCHOR_SCRIPT" --plan "$PLAN" 2>&1) || ANCHOR_EXIT=$?
    ANCHOR_FAILS=$(echo "$ANCHOR_OUTPUT" | grep -c '✗ FAIL' || true)
    ANCHOR_WARNS=$(echo "$ANCHOR_OUTPUT" | grep -c '⚠ WARN' || true)
    if [[ ${ANCHOR_FAILS:-0} -gt 0 ]]; then
        check_fail "$ANCHOR_FAILS anchor(s) could not be verified"
    elif [[ ${ANCHOR_WARNS:-0} -gt 0 ]]; then
        check_warn "$ANCHOR_WARNS stale anchor(s) — re-verify line numbers"
    else
        check_pass "All anchors verified (or none found in plan)"
    fi
else
    check_warn "verify_anchors.sh not found at $ANCHOR_SCRIPT — skipping anchor check"
fi

# ── 2. Agent-prompt blocks present ──────────────────────────────────────
echo "2. Agent-prompt blocks present"
AGENT_BLOCKS=$(echo "$PLAN_CONTENT" | grep -c '```agent' || true)
WORKSTREAMS=$(echo "$PLAN_CONTENT" | grep -c '^### Workstream' || true)
if [[ "$AGENT_BLOCKS" -eq 0 ]]; then
    check_fail "No agent-prompt blocks found in plan (0 blocks)"
elif [[ "$AGENT_BLOCKS" -lt "${WORKSTREAMS:-0}" ]]; then
    check_warn "$AGENT_BLOCKS agent blocks vs $WORKSTREAMS workstreams — some may be missing blocks"
else
    check_pass "$AGENT_BLOCKS agent-prompt blocks present"
fi

# ── 3. No --model in card bodies ────────────────────────────────────────
echo "3. No --model in card bodies"
MODEL_REFS=$(echo "$PLAN_CONTENT" | grep -c '\-\-model' || true)
if [[ "$MODEL_REFS" -gt 0 ]]; then
    # Check if --model appears inside agent blocks (bad) vs outside (ok in docs)
    IN_AGENT=$(echo "$PLAN_CONTENT" | awk '/```agent/,/```/' | grep -c '\-\-model' || true)
    if [[ "$IN_AGENT" -gt 0 ]]; then
        check_fail "$IN_AGENT agent-prompt block(s) contain --model (P005: profile override)"
    else
        check_pass "No --model in agent-prompt blocks"
    fi
else
    check_pass "No --model references found"
fi

# ── 4. Iteration budget estimated ───────────────────────────────────────
echo "4. Iteration budget estimated"
BUDGET_MENTIONS=$(echo "$PLAN_CONTENT" | grep -ci 'turn.*budget\|iteration.*budget\|35 turn\|happy-path.*turn' || true)
if [[ "${BUDGET_MENTIONS:-0}" -gt 0 ]]; then
    check_pass "Iteration budget discussed ($BUDGET_MENTIONS references)"
else
    check_warn "No iteration budget estimates found — cards may exceed 35-turn ceiling"
fi

# ── 5. Monkeypatch paths verified ───────────────────────────────────────
echo "5. Monkeypatch paths verified"
# Check if plan mentions monkeypatch or @patch — if so, confirm dual-patching strategy
MP_MENTIONS=$(echo "$PLAN_CONTENT" | grep -ci 'monkeypatch\|@patch' || true)
if [[ "${MP_MENTIONS:-0}" -gt 0 ]]; then
    DUAL_PATCH=$(echo "$PLAN_CONTENT" | grep -ci 'dual.patch\|dual-patch\|both.*patch\|both.*monkey' || true)
    if [[ "${DUAL_PATCH:-0}" -gt 0 ]]; then
        check_pass "Monkeypatch paths accounted for ($MP_MENTIONS references, dual-patch strategy noted)"
    else
        # Check if the plan involves module extraction (which requires dual-patching)
        EXTRACTION=$(echo "$PLAN_CONTENT" | grep -ci 'extract.*function\|move.*function\|relocate\|extract.*module' || true)
        if [[ "${EXTRACTION:-0}" -gt 0 ]]; then
            check_warn "Plan extracts functions but doesn't mention dual-patching strategy"
        else
            check_pass "No monkeypatch concerns detected"
        fi
    fi
else
    check_pass "No monkeypatch concerns detected"
fi

# ── 6. Contradictions checked ───────────────────────────────────────────
echo "6. Cross-section contradictions checked"
CONFLICT_FLAG=$(python3 "$PLAN_PARSE" workstream-conflict --plan "$PLAN" 2>/dev/null || echo "0")

if [[ "$CONFLICT_FLAG" -eq 1 ]]; then
    check_warn "Same file appears in multiple workstreams — verify no conflicting changes. Run verify_contradictions.sh if available."
else
    check_pass "No cross-section file conflicts detected"
fi

# ── 7. Line budget computed ─────────────────────────────────────────────
echo "7. Line budget computed in YAML frontmatter"
# Check for line_budget in YAML frontmatter
if echo "$PLAN_CONTENT" | grep -q 'line_budget:'; then
    ENTRIES=$(echo "$PLAN_CONTENT" | grep -c 'ws.*:.*{add:' || true)
    check_pass "Line budget present ($ENTRIES entries)"
else
    check_warn "No line_budget found in YAML frontmatter"
fi

# ── 8. Contingencies table present ──────────────────────────────────────
echo "8. Contingencies table present"
if echo "$PLAN_CONTENT" | grep -q '\bRisk\b.*\bProbability\b.*\bImpact\b.*\bMitigation\b'; then
    check_pass "Contingencies table present"
else
    check_warn "No contingencies table found — sad-path risks not documented"
fi

# ── 9. Same-provider staggering noted ────────────────────────────────────
echo "9. Same-provider staggering noted"
PROVIDER_MENTIONS=$(echo "$PLAN_CONTENT" | grep -ci 'provider.*stag\|same.*provider\|rate.limit.*stagg\|serializ.*via parent\|serializ.*provider' || true)
if [[ "${PROVIDER_MENTIONS:-0}" -gt 0 ]]; then
    check_pass "Provider staggering referenced ($PROVIDER_MENTIONS mentions)"
else
    check_warn "No provider staggering strategy mentioned — same-provider cards may stampede"
fi

# ── 10. Dependencies explicit ────────────────────────────────────────────
echo "10. Dependencies explicit"
DEP_GRAPH=$(echo "$PLAN_CONTENT" | grep -c 'parent.*WS\|depends on.*WS\|## Dependency Graph' || true)
if [[ "${DEP_GRAPH:-0}" -gt 0 ]]; then
    check_pass "Dependencies documented ($DEP_GRAPH references)"
else
    check_warn "No dependency graph or parent-child relationships documented"
fi

# ── 11. Goal-card annotations ─────────────────────────────────────────────
echo "11. Goal-card annotations (Hermes ≥ 0.16.0 --goal)"
GOAL_SCRIPT="$SCRIPT_DIR/verify_goal_cards.py"
if [[ -f "$GOAL_SCRIPT" ]]; then
    if python3 "$GOAL_SCRIPT" --plan "$PLAN" 2>&1; then
        check_pass "goal_card annotations valid (or none declared)"
    else
        check_fail "goal_card verification failed — see verify_goal_cards.py output"
    fi
else
    check_warn "verify_goal_cards.py missing — skip goal_card check"
fi

# ── 12. Simplification scan / compaction ──────────────────────────────────
echo "12. Simplification scan / compaction completed"
SIMPLIFY_MENTIONS=$(echo "$PLAN_CONTENT" | grep -ci 'compacted\|simplif\|What can be compacted\|already.*shipped\|SHIPPED' || true)
if [[ "${SIMPLIFY_MENTIONS:-0}" -gt 0 ]]; then
    check_pass "Simplification/compaction evidence found ($SIMPLIFY_MENTIONS references)"
else
    check_warn "No simplification scan or compaction evidence — plan may contain unnecessary analysis steps. See kanban-planning Harden item 11."
fi

# ── 13. Holistic vs Surgical classification ───────────────────────────────
echo "13. Holistic vs Surgical classification"
HOLISTIC_MENTIONS=$(echo "$PLAN_CONTENT" | grep -ci 'holistic.*fix\|holistic.*surgical\|Holistic.*Surgical\|fix classification' || true)
SIGNAL_MAP=$(echo "$PLAN_CONTENT" | grep -ci 'Signal map\|signal map\|Type.*Effort\|classification' || true)
if [[ "${HOLISTIC_MENTIONS:-0}" -gt 0 ]]; then
    check_pass "Holistic/surgical classification found ($HOLISTIC_MENTIONS references)"
elif [[ "${SIGNAL_MAP:-0}" -gt 0 ]]; then
    check_warn "Signal map present but no explicit holistic/surgical classification — add a Type column. See kanban-planning Harden item 12."
else
    check_warn "No fix classification (holistic vs surgical) found — decomposition ordering may be suboptimal. See kanban-planning Harden item 12."
fi

# ── 14. Executive summary documentation-ready ─────────────────────────────
echo "14. Executive summary documentation-ready"
# Check for the six-part documentation pattern: opening + root causes + already-shipped + phases + targets + blast radius
ROOT_CAUSES=$(echo "$PLAN_CONTENT" | grep -ci 'Root cause.*Impact.*Fix complex\|root causes.*three tier\|Root causes.*table' || true)
ALREADY_SHIPPED=$(echo "$PLAN_CONTENT" | grep -ci 'already.*fixed\|already.*shipped\|SHIPPED\|zero action needed' || true)
PHASE_TABLE=$(echo "$PLAN_CONTENT" | grep -ci 'Phase.*Items.*Files.*Target\|Remediation at a glance\|phase.*table' || true)
PERF_TARGETS=$(echo "$PLAN_CONTENT" | grep -ci 'performance.*target\|key.*performance\|before.*after.*target' || true)
BLAST_RADIUS=$(echo "$PLAN_CONTENT" | grep -ci 'blast.*radius\|total.*blast\|files.*zero schema' || true)

DOC_SCORE=0
[[ "${ROOT_CAUSES:-0}" -gt 0 ]] && ((DOC_SCORE++))
[[ "${ALREADY_SHIPPED:-0}" -gt 0 ]] && ((DOC_SCORE++))
[[ "${PHASE_TABLE:-0}" -gt 0 ]] && ((DOC_SCORE++))
[[ "${PERF_TARGETS:-0}" -gt 0 ]] && ((DOC_SCORE++))
[[ "${BLAST_RADIUS:-0}" -gt 0 ]] && ((DOC_SCORE++))

if [[ "$DOC_SCORE" -ge 4 ]]; then
    check_pass "Executive summary documentation-ready ($DOC_SCORE/5 patterns)"
elif [[ "$DOC_SCORE" -ge 2 ]]; then
    check_warn "Executive summary partially documentation-ready ($DOC_SCORE/5 patterns) — see kanban-planning Optimize item 18"
else
    check_warn "Executive summary not documentation-ready ($DOC_SCORE/5 patterns) — flat severity table anti-pattern likely. See kanban-planning Optimize item 18."
fi

# ── 15. Kanban optimization — sequential Card N labeling ─────────────────
echo "15. Kanban optimization — sequential Card N labeling"
OPT_SECTION=$(awk '/^## Kanban optimization/{p=1; next} p && /^## /{exit} p' "$PLAN")
if [[ -z "$OPT_SECTION" ]]; then
    check_fail "No '## Kanban optimization' section — add ordered #### Card 1..N blocks (arrange first, label second)"
else
    BAD_LABELS=$(echo "$OPT_SECTION" | grep -cE '^#### (Workstream|WS[0-9 ]|Card [A-Za-z])' || true)
    if [[ "${BAD_LABELS:-0}" -gt 0 ]]; then
        check_fail "Kanban optimization uses non-standard headings ($BAD_LABELS) — use #### Card 1, Card 2, … integers only"
    else
        ORDINAL_JSON=$(python3 "$PLAN_PARSE" card-ordinals --plan "$PLAN" --json 2>/dev/null || echo '{"ordinals":[],"error":"parse failed"}')
        ORDINAL_ERR=$(echo "$ORDINAL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error') or '')" 2>/dev/null || echo "parse failed")
        APPEAR_ORDER=($(echo "$ORDINAL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(str(x) for x in d.get('ordinals',[])))" 2>/dev/null || true))
        if [[ -n "$ORDINAL_ERR" ]]; then
            check_fail "Card ordinals out of sequence: $ORDINAL_ERR"
        elif [[ ${#APPEAR_ORDER[@]} -eq 0 ]]; then
            check_fail "Kanban optimization has no '#### Card N' headings"
        else
            last="${APPEAR_ORDER[-1]}"
            check_pass "Kanban optimization: Card 1..$last sequential (${#APPEAR_ORDER[@]} cards, dispatch order)"
        fi
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASSES passed, $WARNINGS warnings, $FAILURES failures ==="

EXIT_CODE=0
if [[ $FAILURES -gt 0 ]]; then
    red "BLOCKED: $FAILURES check(s) failed. Fix before declaring 'plan optimized.'"
    EXIT_CODE=1
elif [[ $FAILURES -eq 0 ]] && ! governance_failures_block && [[ $WARNINGS -gt 0 ]]; then
    yellow "PASS (advisory): $WARNINGS advisory check(s). Review before decomposition."
fi

if [[ $WARNINGS -gt 0 ]]; then
    if [[ "$STRICT" == "true" ]]; then
        yellow "BLOCKED (strict mode): $WARNINGS warning(s) treated as failures."
        EXIT_CODE=1
    else
        yellow "PASS with $WARNINGS warning(s). Review warnings before decomposition."
    fi
fi

if [[ $FAILURES -eq 0 ]] && [[ $WARNINGS -eq 0 ]]; then
    green "PASS: All optimization checks passed. Plan ready for decomposition."
fi

exit $EXIT_CODE
