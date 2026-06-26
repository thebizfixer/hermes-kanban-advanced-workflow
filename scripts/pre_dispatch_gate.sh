#!/usr/bin/env bash
# pre_dispatch_gate.sh — single gate before kanban decomposition
# Usage: bash pre_dispatch_gate.sh <plan_id>
set -euo pipefail
export LC_ALL=C.UTF-8

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

# Normalize Windows backslash paths to forward slashes (safe no-op on Linux/macOS).
# Must happen AFTER all variables are set but BEFORE they're used in eval/interpolation.
HERMES_HOME="$(echo "$HERMES_HOME" | tr '\\' '/')"
REPO_ROOT="$(echo "$REPO_ROOT" | tr '\\' '/')"

if [[ -f "$OVERLAY_CONFIG" ]]; then
  _wb="$(grep -E '^working_branch:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^working_branch: *//; s/^"//; s/"$//')"
  [[ -n "$_wb" ]] && WORKING_BRANCH="$_wb"
  _pm="$(grep -E '^plan_memory_path:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^plan_memory_path: *//; s/^"//; s/"$//')"
  [[ -n "$_pm" ]] && PLAN_MEMORY_PATH="$_pm"
  _bp="$(grep -E '^bundle_path:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^bundle_path: *//; s/^"//; s/"$//')"
  [[ -n "$_bp" ]] && BUNDLE_PATH="$_bp"
fi

# Normalize BUNDLE_PATH AFTER overlay override (backslashes from config must be converted)
BUNDLE_PATH="$(echo "$BUNDLE_PATH" | tr '\\' '/')"

FAILURES=0
WARNINGS=0

# Prune stale git worktree registrations BEFORE any dispatch.
# Phantom registrations (path missing but git metadata present) cause
# "already registered worktree" errors on spawn, particularly on Windows.
echo -n "[GATE] worktree_prune ... "
git worktree prune --expire=now 2>/dev/null && echo "PASS" || echo "WARN (non-blocking)"

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
  "PREFLIGHT_SKIP_CODING_AGENT_CLI=\${PREFLIGHT_SKIP_CODING_AGENT_CLI:-} PREFLIGHT_SKIP_MEMORY_BUDGET=\${PREFLIGHT_SKIP_MEMORY_BUDGET:-} bash ${BUNDLE_PATH}/scripts/preflight.sh 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); assert d['status'] in ('pass','degraded')\""

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
    "python3 ${BUNDLE_PATH}/scripts/validate_card_bodies.py --plan '${PLAN_REL}' --repo-root '${REPO_ROOT}' --dry-run"
elif [[ -n "$PLAN_ID" && -f "${BUNDLE_PATH}/scripts/validate_card_bodies.py" ]]; then
  check "card_bodies_fidelity" \
    "python3 ${BUNDLE_PATH}/scripts/validate_card_bodies.py --plan-id '${PLAN_ID}' --repo-root '${REPO_ROOT}' --dry-run"
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

if [[ -f "${BUNDLE_PATH}/scripts/lib/gate_completion_guard.sh" ]]; then
  check "gate_completion_guard" \
    "bash ${BUNDLE_PATH}/scripts/lib/gate_completion_guard.sh"
fi

# Detect stale tasks from prior runs with same plan_id.
# Set ARCHIVE_STALE=1 to auto-archive them; otherwise warns and blocks.
check "stale_tasks" \
  "python3 -c \"
import sqlite3, os, sys
db_path = os.path.join(os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes')), 'kanban.db')
if not os.path.exists(db_path):
    print('PASS: no kanban.db')
    sys.exit(0)
db = sqlite3.connect(db_path)
plan_id = '\${PLAN_ID}'
rows = db.execute('''SELECT id, title, status, created_at FROM tasks
  WHERE status != \\\"archived\\\"
  AND body LIKE \\\"%\\\" || ? || \\\"%\\\"''', (plan_id,)).fetchall()
if not rows:
    print('PASS: no tasks for this plan_id')
    sys.exit(0)
timestamps = [r[3] for r in rows if r[3]]
if not timestamps:
    sys.exit(0)
most_recent = max(timestamps)
cutoff = most_recent - 86400  # 24h
stale = [(r[0], r[1][:60], r[2]) for r in rows if r[3] and r[3] < cutoff]
if not stale:
    print('PASS: no stale tasks from prior runs')
    sys.exit(0)
archive_stale = os.environ.get('ARCHIVE_STALE', '0') == '1'
if archive_stale:
    stale_ids = [s[0] for s in stale]
    placeholders = ','.join(['?'] * len(stale_ids))
    db.execute(f'UPDATE tasks SET status=\\\"archived\\\" WHERE id IN ({placeholders})', stale_ids)
    db.commit()
    print(f'ARCHIVED: {len(stale_ids)} stale tasks')
    for tid, title, status in stale[:10]:
        print(f'  {tid} [{status}] {title}')
    sys.exit(0)
else:
    print(f'WARN: {len(stale)} stale tasks from prior run(s). Set ARCHIVE_STALE=1 to auto-archive.')
    for tid, title, status in stale[:10]:
        print(f'  {tid} [{status}] {title}')
    sys.exit(1)
db.close()
\""

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
