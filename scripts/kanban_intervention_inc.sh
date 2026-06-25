#!/usr/bin/env bash
# Increment the kanban intervention counter and optionally append structured JSONL.
#
# Writes to the project's .hermes/kanban/logs/interventions.count
# (same directory as postmortem reports, attestation, and token log).
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/kanban_intervention_inc.sh
#   bash scripts/kanban_intervention_inc.sh --plan-id PLAN --task-id t_abc --reason "..." --failure-class auth_error

set -euo pipefail

PLAN_ID=""
TASK_ID=""
REASON=""
FAILURE_CLASS="manual"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --task-id) TASK_ID="${2:-}"; shift 2 ;;
    --reason) REASON="${2:-}"; shift 2 ;;
    --failure-class) FAILURE_CLASS="${2:-manual}"; shift 2 ;;
    *) shift ;;
  esac
done

# Find project root by walking up from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
for _ in {1..6}; do
    if [[ -d "$PROJECT_ROOT/.hermes/kanban" ]]; then
        break
    fi
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done

if [[ -n "$PLAN_ID" ]]; then
    LOGDIR="$PROJECT_ROOT/.hermes/kanban/logs/$PLAN_ID"
else
    LOGDIR="$PROJECT_ROOT/.hermes/kanban/logs"
fi
COUNTER="$LOGDIR/interventions.count"
JSONL="$LOGDIR/interventions.jsonl"

mkdir -p "$LOGDIR"

if [[ -f "$COUNTER" ]]; then
    count=$(<"$COUNTER")
    if [[ "$count" =~ ^[0-9]+$ ]]; then
        new=$((count + 1))
    else
        new=1
    fi
else
    new=1
fi

echo "$new" > "$COUNTER"

if [[ -n "$PLAN_ID" || -n "$TASK_ID" || -n "$REASON" ]]; then
  python3 - "$JSONL" "$PLAN_ID" "$TASK_ID" "$FAILURE_CLASS" "$REASON" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
entry = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "plan_id": sys.argv[2] or None,
    "task_id": sys.argv[3] or None,
    "failure_class": sys.argv[4] or "manual",
    "reason": sys.argv[5] or "",
    "source": "kanban_intervention_inc.sh",
}
path.parent.mkdir(parents=True, exist_ok=True)
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")
PY
fi

echo "$new"
