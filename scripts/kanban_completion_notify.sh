#!/usr/bin/env bash
# kanban_completion_notify.sh — one-shot plan-complete gateway summary (non-intervention).
#
# Usage: bash scripts/kanban_completion_notify.sh --plan-id ID [--postmortem PATH] [--done N]
# Config: walk_away_mode in kanban-config.yaml (default false) or legacy NOTIFY_ON_COMPLETE
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}"
POSTMORTEM=""
DONE_COUNT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --postmortem) POSTMORTEM="${2:-}"; shift 2 ;;
    --done) DONE_COUNT="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! _load_branch_config "$REPO_ROOT" 2>/dev/null; then
  exit 0
fi

ENABLED=false
if _walk_away_mode_enabled "$CONFIG_FILE"; then
  ENABLED=true
fi
if [[ "$ENABLED" != "true" ]]; then
  exit 0
fi

if [[ -z "$PLAN_ID" ]]; then
  echo "[kanban_completion_notify] SKIP: plan_id required" >&2
  exit 0
fi

LOG_DIR="$(kanban_logs_dir "$REPO_ROOT")"
mkdir -p "$LOG_DIR"
SENTINEL="${LOG_DIR}/completion_notified_${PLAN_ID}"
if [[ -f "$SENTINEL" ]]; then
  exit 0
fi

if [[ -z "$POSTMORTEM" ]]; then
  reports="${REPO_ROOT}/.hermes/kanban/reports"
  if [[ -d "$reports" ]]; then
    POSTMORTEM="$(find "$reports" -maxdepth 1 -type f -name "${PLAN_ID}_postmortem_*.md" 2>/dev/null | sort | tail -1 || true)"
    if [[ -z "$POSTMORTEM" ]]; then
      POSTMORTEM="$(find "$reports" -maxdepth 1 -type f -name "*${PLAN_ID}*postmortem*.md" 2>/dev/null | sort | tail -1 || true)"
    fi
  fi
fi

if [[ -z "$DONE_COUNT" ]]; then
  DONE_COUNT="$(hermes kanban list 2>/dev/null | grep -c '^✓' || true)"
  if [[ -z "$DONE_COUNT" || "$DONE_COUNT" == "0" ]]; then
    DONE_COUNT="all"
  fi
fi

REL_POSTMORTEM="${POSTMORTEM}"
if [[ -n "$POSTMORTEM" && "$POSTMORTEM" == "$REPO_ROOT"/* ]]; then
  REL_POSTMORTEM="${POSTMORTEM#"$REPO_ROOT"/}"
fi

MSG="✅ Kanban plan complete — ${PLAN_ID}

${DONE_COUNT} tasks done"
if [[ -n "$REL_POSTMORTEM" ]]; then
  MSG="${MSG} · postmortem: ${REL_POSTMORTEM}"
fi
MSG="${MSG}
Board archived. Review postmortem when back."

echo "$MSG"

# Resolve deliver for gateway routing (same as lifecycle)
DELIVER="local"
if [[ -x "$SCRIPT_DIR/lib/resolve_notify_deliver.sh" ]]; then
  DELIVER="$(bash "$SCRIPT_DIR/lib/resolve_notify_deliver.sh" "$REPO_ROOT" 2>/dev/null || echo "local")"
fi

# Explicit gateway delivery for walk-away completion (non-intervention)
if [[ "$DELIVER" != "local" ]]; then
  # Use Hermes send_message (referenced in kanban-notify skill) for direct delivery
  # Graceful fallback if subcommand or flags differ in this Hermes build
  if command -v hermes >/dev/null 2>&1; then
    hermes send_message "$MSG" --deliver "$DELIVER" 2>&1 || \
    hermes send_message "$MSG" 2>&1 || \
    echo "[kanban_completion_notify] Note: delivery attempted via resolved channel $DELIVER (check gateway)"
  else
    echo "[kanban_completion_notify] Hermes CLI not found for direct send (resolved deliver: $DELIVER)"
  fi
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" >"$SENTINEL"
