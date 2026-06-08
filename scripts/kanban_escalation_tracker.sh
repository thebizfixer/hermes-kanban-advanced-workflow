#!/usr/bin/env bash
# kanban_escalation_tracker.sh — Per-card escalation state machine.
#
# Usage:
#   bash kanban_escalation_tracker.sh --task-id <id> --block-reason "<reason>" [--config <file>]
#
# Output (stdout, one line):
#   ESCALATE:<task_id>:<from_level>:<to_level>
#   HUMAN_INTERVENTION:<task_id>:<reason>
#   SILENT:<task_id>
#
# RETRY is handled internally (auto-unblock); not written to stdout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"

TASK_ID=""
BLOCK_REASON=""
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

while [ $# -gt 0 ]; do
    case "$1" in
        --task-id) TASK_ID="$2"; shift 2 ;;
        --block-reason) BLOCK_REASON="$2"; shift 2 ;;
        --config) export HERMES_KANBAN_CONFIG="$2"; shift 2 ;;
        --repo-root) REPO_ROOT="$2"; shift 2 ;;
        *) echo "[kanban-governance] ERROR: unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [ -z "$TASK_ID" ]; then
    echo "[kanban-governance] ERROR: --task-id required" >&2
    exit 1
fi

CONFIG_FILE="$(_resolve_kanban_config_file "$REPO_ROOT" || true)"
if [ -z "$CONFIG_FILE" ] || [ ! -f "$CONFIG_FILE" ]; then
    echo "[kanban-governance] ERROR: config not found — run hermes kanban-advanced init" >&2
    exit 1
fi

if ! _load_escalation_config "$CONFIG_FILE"; then
    exit 1
fi

ESCALATION_DIR="${HERMES_HOME}/kanban/escalation"
mkdir -p "$ESCALATION_DIR"
STATE_FILE="$ESCALATION_DIR/${TASK_ID}.json"
LOG_FILE="${KANBAN_ESCALATION_LOG:-$HERMES_HOME/kanban/logs/escalation.log}"
mkdir -p "$(dirname "$LOG_FILE")"

RESULT=$(python3 - "$TASK_ID" "$BLOCK_REASON" "$STATE_FILE" \
    "$ESCALATION_MAX_CODING_AGENT" "$ESCALATION_MAX_WORKER" "$ESCALATION_MAX_ORCHESTRATOR" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

task_id, block_reason, state_path = sys.argv[1], sys.argv[2], sys.argv[3]
max_coding, max_worker, max_orch = map(int, sys.argv[4:7])
path = Path(state_path)

tag_re = re.compile(r"\[escalation:(coding_agent|worker|orchestrator):attempt:(\d+)\]", re.I)
m = tag_re.search(block_reason or "")
level = m.group(1).lower() if m else "coding_agent"
attempt = int(m.group(2)) if m else 1

now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
state = {"task_id": task_id, "level": level, "attempts_at_level": attempt, "last_attempt": now, "history": []}
if path.exists():
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pass

state["level"] = level
state["attempts_at_level"] = attempt
state["last_attempt"] = now
state.setdefault("history", [])
state["history"].append(
    {"level": level, "attempts": attempt, "block_reason": block_reason, "timestamp": now}
)

thresholds = {
    "coding_agent": max_coding,
    "worker": max_worker,
    "orchestrator": max_orch,
}

def is_catastrophic(reason: str) -> bool:
    r = (reason or "").lower()
    markers = (
        "auth_failure", "missing_profile", "manual_judgment", "memory_budget",
        "ci_red_after_push", "credential", "unreachable", "infrastructure",
        "e007", "e008", "e011", "e012", "e013", "p001",
    )
    return any(m in r for m in markers)

max_at_level = thresholds.get(level, max_coding)
path.write_text(json.dumps(state, indent=2), encoding="utf-8")

if attempt < max_at_level:
  print(f"RETRY:{task_id}:{level}:{attempt}")
  sys.exit(0)

# Threshold reached — escalate
next_level = {
    "coding_agent": "worker",
    "worker": "orchestrator",
    "orchestrator": "human",
}.get(level, "worker")

if next_level == "human" or (level == "orchestrator" and attempt >= max_orch):
    if is_catastrophic(block_reason):
        print(f"HUMAN_INTERVENTION:{task_id}:{block_reason[:200]}")
    else:
        print(f"ESCALATE:{task_id}:{level}:plan_review")
    sys.exit(0)

print(f"ESCALATE:{task_id}:{level}:{next_level}")
PY
)

echo "$RESULT" >> "$LOG_FILE"

case "$RESULT" in
    RETRY:*)
        # Auto-unblock below threshold — not sent to LLM stdout
        hermes kanban unblock "$TASK_ID" \
            --reason "auto-retry at ${RESULT#RETRY:}" 2>/dev/null || true
        echo "SILENT:$TASK_ID" >&2
        ;;
    ESCALATE:*|HUMAN_INTERVENTION:*)
        echo "$RESULT"
        ;;
    *)
        echo "SILENT:$TASK_ID"
        ;;
esac
