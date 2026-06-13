#!/usr/bin/env bash
# governance_integrity.sh — verify the full governance layer is intact.
# Checks: scripts exist + executable, registry valid, policies present, prompts present.
# Run before decomposition as part of preflight. Exit 0 = pass, exit 1 = blocking.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh
#   bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh --json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS_DIR="$BUNDLE_DIR/scripts"
REGISTRY_DIR="$BUNDLE_DIR/registry"
POLICIES_DIR="$BUNDLE_DIR/policies"
PROMPTS_DIR="$BUNDLE_DIR/prompts"
SKILLS_DIR="$BUNDLE_DIR/skills"

JSON_OUT=false
[[ "${1:-}" == "--json" ]] && JSON_OUT=true

FAILURES=0
WARNINGS=0
CHECKS_PASSED=0

pass() { CHECKS_PASSED=$((CHECKS_PASSED + 1)); }
fail() { echo "  ✗ FAIL: $*" >&2; FAILURES=$((FAILURES + 1)); }
warn() { echo "  ⚠ WARN: $*" >&2; WARNINGS=$((WARNINGS + 1)); }

# ── 1. Required scripts exist and are executable ────────────────────────
REQUIRED_SCRIPTS=(
    auto_unblock.sh
    board_keeper.sh
    generate_postmortem.py
    git_safe_cleanup.sh
    kanban_attestation.py
    kanban_card_policy.py
    kanban_cron_monitor_log_fallback.sh
    kanban_evaluation_chain.py
    kanban_intervention_inc.sh
    kanban_recover.py
    kanban_token_report.py
    post_merge_gate.sh
    pre_dispatch_gate.sh
    preflight.sh
    provision.sh
    sanity_check.sh
    validate_board.sh
    validate_config.py
    verify_anchors.sh
    verify_anchors.py
    verify_goal_cards.py
    verify_optimization.sh
    worktree_audit.sh
    lib/governance_profile.py
    lib/governance_profile.sh
    lib/plan_parse.py
    lib/cli_output_parse.py
    lib/kanban_cli_parse.sh
    lib/kanban_logs.sh
)

for script in "${REQUIRED_SCRIPTS[@]}"; do
    path="$SCRIPTS_DIR/$script"
    if [[ ! -f "$path" ]]; then
        fail "Missing script: $script"
    elif [[ ! -x "$path" ]] && [[ "$script" != *.py ]]; then
        warn "Script not executable: $script (run: chmod +x $path)"
    else
        pass
    fi
done

# ── 2. Registry files present ───────────────────────────────────────────
REQUIRED_REGISTRY=(error-codes.yaml)
for f in "${REQUIRED_REGISTRY[@]}"; do
    if [[ -f "$REGISTRY_DIR/$f" ]]; then
        pass
    else
        fail "Missing registry: $f"
    fi
done

# ── 3. Policy files present ─────────────────────────────────────────────
REQUIRED_POLICIES=(card-body-policy.yaml)
for f in "${REQUIRED_POLICIES[@]}"; do
    if [[ -f "$POLICIES_DIR/$f" ]]; then
        pass
    else
        fail "Missing policy: $f"
    fi
done

# ── 4. Prompt files present ─────────────────────────────────────────────
REQUIRED_PROMPTS=(orchestrator.md worker.md)
for f in "${REQUIRED_PROMPTS[@]}"; do
    if [[ -f "$PROMPTS_DIR/$f" ]]; then
        pass
    else
        fail "Missing prompt: $f"
    fi
done

# ── 5. Goal-card reference ────────────────────────────────────────────────
if [[ -f "$BUNDLE_DIR/references/goal-card-selection.md" ]]; then
    pass
else
    fail "Missing references/goal-card-selection.md"
fi

# ── 6. Skill files present ──────────────────────────────────────────────
REQUIRED_SKILLS=(kanban-orchestrator.md kanban-worker.md kanban-planning.md 
                 kanban-preflight.md kanban-cleanup.md kanban-notify.md
                 kanban-postmortem.md kanban-reconciliation.md)
for f in "${REQUIRED_SKILLS[@]}"; do
    if [[ -f "$SKILLS_DIR/$f" ]]; then
        pass
    else
        fail "Missing skill: $f"
    fi
done

# ── 7. Provisioning state ───────────────────────────────────────────────
REPO_ROOT="$(cd "$BUNDLE_DIR/.." && pwd)"
PROVISION_RC=0
if pushd "$REPO_ROOT" >/dev/null; then
    bash "$SCRIPTS_DIR/provision.sh" --check || PROVISION_RC=$?
    popd >/dev/null || true
else
    PROVISION_RC=1
fi
if [[ "$PROVISION_RC" -eq 0 ]]; then
    pass
else
    fail "Provisioning drift detected — run provision.sh from repo root to sync materialized skills"
fi

# ── Summary ─────────────────────────────────────────────────────────────
if [[ "$JSON_OUT" == true ]]; then
    echo "{\"pass\":$CHECKS_PASSED,\"failures\":$FAILURES,\"warnings\":$WARNINGS}"
else
    echo ""
    echo "=== Governance Integrity: $CHECKS_PASSED passed, $FAILURES failures, $WARNINGS warnings ==="
fi

[[ $FAILURES -eq 0 ]] && exit 0 || exit 1
