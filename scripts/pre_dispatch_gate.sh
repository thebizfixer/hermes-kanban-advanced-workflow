#!/usr/bin/env bash
# pre_dispatch_gate.sh — single gate before kanban decomposition
# Usage: bash pre_dispatch_gate.sh <plan_id>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"
# shellcheck source=lib/plan_paths.sh
source "$SCRIPT_DIR/lib/plan_paths.sh"

PLAN_ID="${1:-}"
if [ -z "$PLAN_ID" ]; then
  echo "[GATE] ERROR: plan_id required" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

WORKING_BRANCH="${KANBAN_WORKING_BRANCH:-main}"
PLAN_MEMORY_PATH="${KANBAN_PLAN_MEMORY_PATH:-.hermes/kanban/memory}"
BUNDLE_PATH="${KANBAN_BUNDLE_PATH:-hermes-kanban-advanced-workflow}"
OVERLAY_CONFIG="$REPO_ROOT/.hermes/kanban-overrides/kanban-config.yaml"

if [[ -f "$OVERLAY_CONFIG" ]]; then
  _wb="$(grep -E '^working_branch:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^working_branch: *//; s/^"//; s/"$//')"
  [[ -n "$_wb" ]] && WORKING_BRANCH="$_wb"
  _pm="$(grep -E '^plan_memory_path:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^plan_memory_path: *//; s/^"//; s/"$//')"
  [[ -n "$_pm" ]] && PLAN_MEMORY_PATH="$_pm"
  _bp="$(grep -E '^bundle_path:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^bundle_path: *//; s/^"//; s/"$//')"
  [[ -n "$_bp" ]] && BUNDLE_PATH="$_bp"
fi

FAILURES=0
WARNINGS=0

check() {
  local name="$1" cmd="$2"
  echo -n "[GATE] $name ... "
  if eval "$cmd" >/dev/null 2>&1; then
    echo "PASS"
  else
    echo "FAIL"
    FAILURES=$((FAILURES + 1))
  fi
}

warn() {
  local name="$1" cmd="$2"
  echo -n "[GATE] $name ... "
  if eval "$cmd" >/dev/null 2>&1; then
    echo "PASS"
  else
    echo "WARN (non-blocking)"
    WARNINGS=$((WARNINGS + 1))
  fi
}

PLAN_REL="$(resolve_plan_file "$REPO_ROOT" "$PLAN_ID" "" 2>/dev/null || true)"
if [[ -n "$PLAN_REL" ]]; then
  check "plan on ${WORKING_BRANCH}" \
    "git log --oneline -1 -- ${PLAN_REL} | grep -q ."
else
  check "plan on ${WORKING_BRANCH}" \
    "git log --oneline -1 -- .hermes/kanban/plans/*${PLAN_ID}*.md .agent/plans/*${PLAN_ID}*.md 2>/dev/null | grep -q ."
fi

warn "plan pushed" \
  "git fetch origin ${WORKING_BRANCH} --dry-run 2>&1 | grep -q 'up to date'"

warn "preflight" \
  "bash ${BUNDLE_PATH}/scripts/preflight.sh 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); assert d['status'] in ('pass','degraded')\""

if [[ "${PREFLIGHT_SKIP_CODING_AGENT_CLI:-}" == "1" ]]; then
  echo -n "[GATE] coding_agent_cli ... "
  echo "PASS (skipped by PREFLIGHT_SKIP_CODING_AGENT_CLI=1 — audit-noted override)"
else
  check "coding_agent_cli" \
    "cd \"${REPO_ROOT}\" && PYTHONPATH=\"${REPO_ROOT}\" python3 ${BUNDLE_PATH}/scripts/check_coding_agent_cli.py --timeout ${PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT:-15}"
fi

check "attestation" \
  "python3 ${BUNDLE_PATH}/scripts/kanban_attestation.py '${PLAN_ID}' --verify 2>/dev/null | grep -q PASS"

warn "card_policy_script" \
  "test -f ${BUNDLE_PATH}/scripts/kanban_card_policy.py"

check "plan_memory" \
  "test -f ${PLAN_MEMORY_PATH}/${PLAN_ID}.json"

check "kanban_db" \
  "python3 -c \"import sqlite3, os; db_path = os.path.join(os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes')), 'kanban.db'); db=sqlite3.connect(db_path); assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'\" 2>/dev/null"

if [[ -n "$PLAN_REL" && -f "${BUNDLE_PATH}/scripts/validate_card_bodies.py" ]]; then
  check "card_bodies_fidelity" \
    "python3 ${BUNDLE_PATH}/scripts/validate_card_bodies.py --plan '${PLAN_REL}' --repo-root '${REPO_ROOT}'"
elif [[ -n "$PLAN_ID" && -f "${BUNDLE_PATH}/scripts/validate_card_bodies.py" ]]; then
  check "card_bodies_fidelity" \
    "python3 ${BUNDLE_PATH}/scripts/validate_card_bodies.py --plan-id '${PLAN_ID}' --repo-root '${REPO_ROOT}'"
fi

check "cron_scripts" \
  "python3 -c \"import os; hh=os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes')); scripts=os.path.join(hh,'scripts'); exit(0 if all(os.path.isfile(os.path.join(scripts,f)) for f in ['auto_unblock.py','board_keeper.py','worktree_setup.sh']) else 1)\""

check "cron_hermes_path" \
  "PATH=\"${HOME}/.local/bin:${PATH}\" command -v hermes >/dev/null 2>&1"

warn "gateway_running" \
  "hermes cron status 2>&1 | grep -qiE 'running|active'"

if [[ -f "${BUNDLE_PATH}/scripts/cycle_detector.py" ]]; then
  check "cycle_detect" \
    "python3 ${BUNDLE_PATH}/scripts/cycle_detector.py --plan-id '${PLAN_ID}' --repo-root '${REPO_ROOT}'"
fi

echo ""
echo "[GATE] Result: $FAILURES failures, $WARNINGS warnings"
if [ "$FAILURES" -gt 0 ]; then
  echo "[GATE] BLOCKED — fix failures before dispatching"
  exit 1
fi

# Pre-warm Cursor OAuth once so parallel workers inherit a fresh access token.
GATE_LIB_DIR="$SCRIPT_DIR/lib"
[[ "$SCRIPT_DIR" == */lib ]] && GATE_LIB_DIR="$SCRIPT_DIR"
# shellcheck source=lib/coding_agent_env.sh
source "$GATE_LIB_DIR/coding_agent_env.sh" 2>/dev/null || true
# shellcheck source=lib/coding_agent_auth_lock.sh
source "$GATE_LIB_DIR/coding_agent_auth_lock.sh" 2>/dev/null || true
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi
ensure_coding_agent_home 2>/dev/null || true
CODING_AGENT="${KANBAN_CODING_AGENT:-}"
if [[ "$CODING_AGENT" == "agent" || "$CODING_AGENT" == "cursor-agent" ]]; then
  check "coding_agent_auth_prewarm" "prewarm_coding_agent_auth"
else
  warn "coding_agent_auth_prewarm" "prewarm_coding_agent_auth"
fi

echo ""
echo "[GATE] Result: $FAILURES failures, $WARNINGS warnings"
if [ "$FAILURES" -gt 0 ]; then
  echo "[GATE] BLOCKED — fix failures before dispatching"
  exit 1
fi

if [[ -f "${PLAN_MEMORY_PATH}/${PLAN_ID}.json" ]]; then
  warn "plan_memory_fresh" "python3 ${BUNDLE_PATH}/scripts/lib/plan_memory_gate_check.py --memory ${PLAN_MEMORY_PATH}/${PLAN_ID}.json --plan '${PLAN_REL}' --repo-root '${REPO_ROOT}' --bundle-scripts '${BUNDLE_PATH}/scripts'"
fi

echo "[GATE] PASSED — proceed to decomposition"
python3 "${BUNDLE_PATH}/scripts/lib/orchestrator_token_checkpoint.py" \
  --plan-id "${PLAN_ID}" \
  --checkpoint pre-dispatch-gate-pass 2>/dev/null || true
