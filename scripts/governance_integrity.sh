#!/usr/bin/env bash
# governance_integrity.sh — verify the full governance layer is intact.
# Checks: scripts exist + executable, registry valid, policies present, prompts present.
# Run before decomposition as part of preflight. Exit 0 = pass, exit 1 = blocking.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh
#   bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh --json
#
# Resolves plugin checkout layout (plugin/data/*, plugin/skills/*) or legacy flat bundle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR"

JSON_OUT=false
[[ "${1:-}" == "--json" ]] && JSON_OUT=true

FAILURES=0
WARNINGS=0
CHECKS_PASSED=0

pass() { CHECKS_PASSED=$((CHECKS_PASSED + 1)); }
fail() { echo "  ✗ FAIL: $*" >&2; FAILURES=$((FAILURES + 1)); }
warn() { echo "  ⚠ WARN: $*" >&2; WARNINGS=$((WARNINGS + 1)); }

# ── Bundle + data path resolution ───────────────────────────────────────
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_DIR=""
POLICIES_DIR=""
PROMPTS_DIR=""
REFERENCES_DIR=""
SKILLS_DIR=""
SKILL_LAYOUT="plugin"  # plugin | flat

if [[ -d "$BUNDLE_ROOT/plugin/data/registry" ]]; then
    REGISTRY_DIR="$BUNDLE_ROOT/plugin/data/registry"
    POLICIES_DIR="$BUNDLE_ROOT/plugin/data/policies"
    PROMPTS_DIR="$BUNDLE_ROOT/plugin/data/prompts"
    REFERENCES_DIR="$BUNDLE_ROOT/plugin/data/references"
    SKILLS_DIR="$BUNDLE_ROOT/plugin/skills"
elif [[ -d "$BUNDLE_ROOT/registry" ]]; then
    REGISTRY_DIR="$BUNDLE_ROOT/registry"
    POLICIES_DIR="$BUNDLE_ROOT/policies"
    PROMPTS_DIR="$BUNDLE_ROOT/prompts"
    REFERENCES_DIR="$BUNDLE_ROOT/references"
    SKILLS_DIR="$BUNDLE_ROOT/skills"
    SKILL_LAYOUT="flat"
else
    fail "Could not resolve registry directory (expected plugin/data/registry or registry/)"
fi

_resolve_skill_path() {
    local skill="$1"
    if [[ "$SKILL_LAYOUT" == "plugin" ]]; then
        printf '%s/%s/SKILL.md' "$SKILLS_DIR" "$skill"
    else
        printf '%s/%s.md' "$SKILLS_DIR" "$skill"
    fi
}

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
    kanban_layout_acceptance.sh
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
    audit_anchors.sh
    audit_anchors.py
    verify_goal_cards.py
    verify_optimization.sh
    worktree_audit.sh
    lib/governance_profile.py
    lib/governance_profile.sh
    lib/plan_parse.py
    lib/cli_output_parse.py
    lib/kanban_cli_parse.sh
    lib/kanban_logs.sh
    lib/card_body.py
    lib/presentation_acceptance.py
    lib/verify_optimization_presentation.py
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

if [[ -f "$REGISTRY_DIR/error-codes.yaml" ]]; then
    for code in E028 E029; do
        if grep -q "${code}:" "$REGISTRY_DIR/error-codes.yaml"; then
            pass
        else
            fail "Missing error code in registry: $code"
        fi
    done
fi

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

# ── 5. Reference docs ─────────────────────────────────────────────────────
REQUIRED_REFERENCES=(goal-card-selection.md frontend-neutrality.md)
for f in "${REQUIRED_REFERENCES[@]}"; do
    if [[ -f "$REFERENCES_DIR/$f" ]]; then
        pass
    else
        fail "Missing references/$f"
    fi
done

# ── 6. Skill files present ──────────────────────────────────────────────
REQUIRED_SKILLS=(
    kanban-orchestrator
    kanban-worker
    kanban-planning
    kanban-preflight
    kanban-cleanup
    kanban-notify
    kanban-postmortem
    kanban-reconciliation
    kanban-advanced
)
for skill in "${REQUIRED_SKILLS[@]}"; do
    skill_path="$(_resolve_skill_path "$skill")"
    if [[ -f "$skill_path" ]]; then
        pass
    else
        fail "Missing skill: $skill ($skill_path)"
    fi
done

# ── 7. Provisioning state (host project only) ───────────────────────────
REPO_ROOT="${HERMES_KANBAN_REPO_ROOT:-}"
if [[ -z "$REPO_ROOT" ]]; then
    REPO_ROOT="$(git -C "$BUNDLE_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$REPO_ROOT" ]]; then
    REPO_ROOT="$(cd "$BUNDLE_ROOT/.." && pwd)"
fi

OVERLAY="$REPO_ROOT/.hermes/kanban-overrides/kanban-config.yaml"
if [[ -f "$OVERLAY" ]]; then
    PROVISION_RC=0
    if pushd "$REPO_ROOT" >/dev/null; then
        REPO_ROOT="$REPO_ROOT" bash "$SCRIPTS_DIR/provision.sh" --check || PROVISION_RC=$?
        popd >/dev/null || true
    else
        PROVISION_RC=1
    fi
    if [[ "$PROVISION_RC" -eq 0 ]]; then
        pass
    else
        fail "Provisioning drift detected — run provision.sh from repo root to sync materialized skills"
    fi
else
    warn "No host overlay at $OVERLAY — skipping provision.sh --check"
    pass
fi

# ── Summary ─────────────────────────────────────────────────────────────
if [[ "$JSON_OUT" == true ]]; then
    echo "{\"pass\":$CHECKS_PASSED,\"failures\":$FAILURES,\"warnings\":$WARNINGS}"
else
    echo ""
    echo "=== Governance Integrity: $CHECKS_PASSED passed, $FAILURES failures, $WARNINGS warnings ==="
fi

[[ $FAILURES -eq 0 ]] && exit 0 || exit 1
