#!/usr/bin/env bash
# pre_dispatch_gate.sh — single gate before kanban decomposition
# Usage: bash pre_dispatch_gate.sh <plan_id>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"

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

check "plan on ${WORKING_BRANCH}" \
  "git log --oneline -1 -- .cursor/plans/*${PLAN_ID}*.md | grep -q ."

warn "plan pushed" \
  "git fetch origin ${WORKING_BRANCH} --dry-run 2>&1 | grep -q 'up to date'"

warn "preflight" \
  "bash ${BUNDLE_PATH}/scripts/preflight.sh 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); assert d['status'] in ('pass','degraded')\""

check "coding_agent_cli" \
  "cd \"${REPO_ROOT}\" && PYTHONPATH=\"${REPO_ROOT}\" python3 ${BUNDLE_PATH}/scripts/check_coding_agent_cli.py"

check "attestation" \
  "python3 ${BUNDLE_PATH}/scripts/kanban_attestation.py '${PLAN_ID}' --verify 2>/dev/null | grep -q PASS"

warn "card_policy_script" \
  "test -f ${BUNDLE_PATH}/scripts/kanban_card_policy.py"

check "plan_memory" \
  "test -f ${PLAN_MEMORY_PATH}/${PLAN_ID}.json"

check "kanban_db" \
  "python3 -c \"import sqlite3; db=sqlite3.connect('${HERMES_HOME}/kanban.db'); assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'\""

check "cron_scripts" \
  "test -x ${HERMES_HOME}/scripts/auto_unblock.sh && test -x ${HERMES_HOME}/scripts/board_keeper.sh"

check "cron_hermes_path" \
  "PATH=\"${HOME}/.local/bin:${PATH}\" command -v hermes >/dev/null 2>&1"

echo ""
echo "[GATE] Result: $FAILURES failures, $WARNINGS warnings"
if [ "$FAILURES" -gt 0 ]; then
  echo "[GATE] BLOCKED — fix failures before dispatching"
  exit 1
fi
echo "[GATE] PASSED — proceed to decomposition"
