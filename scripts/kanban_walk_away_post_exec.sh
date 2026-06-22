#!/usr/bin/env bash
# kanban_walk_away_post_exec.sh — unattended reconciliation → postmortem → archive → cleanup → notify.
#
# Runs only when walk_away_mode is enabled in kanban-config.yaml (dashboard Cron toggle).
# Idempotent per plan_id via .hermes/kanban/logs/post_exec_complete_<plan_id>.
#
# Usage: bash scripts/kanban_walk_away_post_exec.sh --plan-id ID [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

PLAN_ID=""
DRY_RUN=false

# ── Hard-stop guard: only run when walk_away_mode is true ──
CONFIG_FILE="$(_resolve_kanban_config_file "$REPO_ROOT" 2>/dev/null || echo "")"
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
  WALK_AWAY=$(grep -E '^\s*walk_away_mode:\s*true' "$CONFIG_FILE" 2>/dev/null || true)
  if [ -z "$WALK_AWAY" ]; then
    echo "[hard-stop] walk_away_mode is not true — refusing to run post-exec actions"
    echo "[hard-stop] Reconciliation, postmortem, and cleanup are operator-driven."
    exit 2
  fi
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) shift ;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! _load_branch_config "$REPO_ROOT" 2>/dev/null; then
  exit 0
fi

if ! _walk_away_mode_enabled "$CONFIG_FILE"; then
  exit 0
fi

if [[ -z "$PLAN_ID" ]]; then
  PLAN_ID="$(_resolve_active_plan_id "$REPO_ROOT")"
fi
if [[ -z "$PLAN_ID" ]]; then
  echo "[kanban_walk_away_post_exec] SKIP: plan_id required" >&2
  exit 0
fi

LOG_DIR="$(kanban_logs_dir "$REPO_ROOT")"
mkdir -p "$LOG_DIR"
SENTINEL="${LOG_DIR}/post_exec_complete_${PLAN_ID}"
if [[ -f "$SENTINEL" ]]; then
  exit 0
fi

# Final audit card must be done before post-exec.
AUDIT_DONE=false
while IFS= read -r line; do
  tid="$(echo "$line" | awk '{print $2}')"
  [[ -z "$tid" ]] && continue
  title="$(hermes kanban show "$tid" 2>/dev/null | grep -m1 "Task $tid:" || true)"
  if echo "$title" | grep -qiE 'final[ -]audit'; then
    AUDIT_DONE=true
    break
  fi
done < <(hermes kanban list 2>/dev/null | grep '^✓' || true)

if [[ "$AUDIT_DONE" != "true" ]]; then
  echo "[kanban_walk_away_post_exec] WAIT: final audit not done (plan_id=${PLAN_ID})" >&2
  exit 0
fi

echo "[kanban_walk_away_post_exec] plan_id=${PLAN_ID} — starting unattended post-execution"

DONE_COUNT="$(hermes kanban list 2>/dev/null | grep -c '^✓' || true)"
REPORTS_DIR="${REPO_ROOT}/.hermes/kanban/reports"
mkdir -p "$REPORTS_DIR"

# 1. RECONCILIATION (HARD GATE before postmortem).
# Must succeed for the plan before we generate postmortem or archive.
RECONCILE_OK=true
if [[ -f "$SCRIPT_DIR/kanban_token_report.py" ]]; then
  echo " Token report (reconciliation artifact)..."
  if [[ "$DRY_RUN" == "false" ]]; then
    if ! python3 "$SCRIPT_DIR/kanban_token_report.py" --plan "$PLAN_ID" 2>&1; then
      echo "[kanban_walk_away_post_exec] Token report failed"
      RECONCILE_OK=false
    fi
  fi
fi

# Basic additional reconciliation sanity (file compliance via final audit report if present)
if [[ "$DRY_RUN" == "false" ]]; then
  REPORTS_DIR="${REPO_ROOT}/.hermes/kanban/reports"
  if [[ ! -f "$REPORTS_DIR/${PLAN_ID}_kpi.json" && ! -f "$REPORTS_DIR/${PLAN_ID}_postmortem_"*".md" ]]; then
    # Allow first run; token report is the primary gate for walk-away
    : 
  fi
fi

if [[ "$RECONCILE_OK" != "true" ]]; then
  echo "[kanban_walk_away_post_exec] BLOCK: reconciliation failed — do not proceed to postmortem"
  exit 1
fi

# 2. POSTMORTEM (only after successful reconciliation).
POSTMORTEM=""
if [[ -f "$SCRIPT_DIR/generate_postmortem.py" ]]; then
  echo "→ Generating postmortem..."
  if [[ "$DRY_RUN" == "false" ]]; then
    python3 "$SCRIPT_DIR/generate_postmortem.py" \
      --plan-id "$PLAN_ID" \
      --output "$REPORTS_DIR/" 2>&1 || true
    POSTMORTEM="$(find "$REPORTS_DIR" -maxdepth 1 -type f -name "${PLAN_ID}_postmortem_*.md" 2>/dev/null | sort | tail -1 || true)"
  fi
fi

# 3. Archive board + remove wave crons.
if [[ -f "$SCRIPT_DIR/provision_kanban_crons.sh" ]]; then
  echo "→ Removing wave crons..."
  if [[ "$DRY_RUN" == "false" ]]; then
    bash "$SCRIPT_DIR/provision_kanban_crons.sh" --remove --plan-id "$PLAN_ID" 2>&1 || true
  fi
fi

echo "→ Archiving kanban tasks..."
if [[ "$DRY_RUN" == "false" ]]; then
  while IFS= read -r line; do
    tid="$(echo "$line" | awk '{print $2}')"
    [[ -z "$tid" ]] && continue
    hermes kanban archive "$tid" 2>/dev/null || true
  done < <(hermes kanban list 2>/dev/null | grep -E '^(✓|●|▶|⊘|◻)' || true)
fi

# 4. Git-safe cleanup (best-effort).
if [[ -x "$SCRIPT_DIR/git_safe_cleanup.sh" ]]; then
  echo "→ Git-safe cleanup..."
  if [[ "$DRY_RUN" == "false" ]]; then
    bash "$SCRIPT_DIR/git_safe_cleanup.sh" --clean --staging "$WORKING_BRANCH" 2>&1 || true
  else
    bash "$SCRIPT_DIR/git_safe_cleanup.sh" --clean --dry-run --staging "$WORKING_BRANCH" 2>&1 || true
  fi
fi

# 5. Completion notify (walk-away mode implies notify on success).
if [[ "$DRY_RUN" == "false" ]]; then
  bash "$SCRIPT_DIR/kanban_completion_notify.sh" \
    --plan-id "$PLAN_ID" \
    --done "${DONE_COUNT:-all}" \
    ${POSTMORTEM:+--postmortem "$POSTMORTEM"} 2>&1 || true
  date -u +"%Y-%m-%dT%H:%M:%SZ" >"$SENTINEL"
fi

echo "[kanban_walk_away_post_exec] complete (plan_id=${PLAN_ID})"
