#!/usr/bin/env bash
# kanban_lifecycle_notify.sh — per-card lifecycle notifications (after gate done).
#
# Usage: bash scripts/kanban_lifecycle_notify.sh [--plan-id ID]
# Config: notify_lifecycle in kanban-config.yaml (default true) or NOTIFY_LIFECYCLE=true
set -euo pipefail
export PYTHONIOENCODING=utf-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}"
BOARD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --board) BOARD="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done
export KANBAN_BOARD="${BOARD:-${KANBAN_BOARD:-}}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Read PLAN_ID from plan memory (per-plan tracking) or fall back to legacy singleton
if [[ -z "$PLAN_ID" ]]; then
  for f in "$REPO_ROOT/.hermes/kanban/memory/"*.json; do
    [[ -f "$f" ]] || continue
    PLAN_ID="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('plan_id',''))" "$f" 2>/dev/null || true)"
    [[ -n "$PLAN_ID" ]] && break
  done
fi
if [[ -z "$PLAN_ID" && -f "$REPO_ROOT/.hermes/kanban/logs/lifecycle_plan_id" ]]; then
  PLAN_ID="$(<"$REPO_ROOT/.hermes/kanban/logs/lifecycle_plan_id")"
fi
if ! _load_branch_config "$REPO_ROOT" 2>/dev/null; then
  exit 0
fi

ENABLED="${NOTIFY_LIFECYCLE:-}"
if [[ -z "$ENABLED" && -f "$CONFIG_FILE" ]]; then
  ENABLED="$(grep -E '^[[:space:]]*notify_lifecycle:' "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/.*: *//; s/^"//; s/"$//' || true)"
fi
if [[ -z "$ENABLED" ]]; then
  ENABLED="true"
fi
if [[ "$ENABLED" != "true" && "$ENABLED" != "1" ]]; then
  exit 0
fi

LOG_DIR="$(kanban_logs_dir "$REPO_ROOT")"
mkdir -p "$LOG_DIR"

export KANBAN_LIFECYCLE_PLAN_ID="$PLAN_ID"
export KANBAN_LIFECYCLE_STATE="${LOG_DIR}/lifecycle_state.json"
export KANBAN_LIFECYCLE_LOG="${LOG_DIR}/lifecycle.jsonl"

python3 - <<'PY'
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

plan_id = os.environ.get("KANBAN_LIFECYCLE_PLAN_ID", "")
state_path = Path(os.environ["KANBAN_LIFECYCLE_STATE"])
log_path = Path(os.environ["KANBAN_LIFECYCLE_LOG"])


def read_state() -> dict:
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_state_atomic(data: dict) -> None:
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(state_path)


def hermes_list() -> str:
    board = os.environ.get("KANBAN_BOARD", "").strip()
    if not board and plan_id:
        # Auto-resolve board via resolver singleton
        try:
            from lib.board_resolver import resolve_board_for_plan  # noqa: E402
            resolved = resolve_board_for_plan(plan_id)
            if resolved:
                board = resolved
                os.environ["KANBAN_BOARD"] = board
        except ImportError:
            pass
    if board:
        return subprocess.run(
            ["hermes", "kanban", "--board", board, "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout
    return subprocess.run(
        ["hermes", "kanban", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def hermes_show(tid: str) -> str:
    board = os.environ.get("KANBAN_BOARD", "").strip()
    if board:
        return subprocess.run(
            ["hermes", "kanban", "--board", board, "show", tid],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout
    return subprocess.run(
        ["hermes", "kanban", "show", tid], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def board_counts(text: str) -> tuple[int, int, int]:
    done = sum(1 for line in text.splitlines() if line.startswith("✓"))
    active = sum(1 for line in text.splitlines() if line.startswith(("●", "▶")))
    blocked = sum(1 for line in text.splitlines() if line.startswith("⊘"))
    return done, active, blocked


def snapshot_board() -> dict:
    listing = hermes_list()
    cards: dict[str, dict] = {}
    gate_done = False
    sym_map = {"✓": "done", "●": "running", "▶": "ready", "⊘": "blocked", "◻": "todo"}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[1].startswith("t_"):
            continue
        sym, tid = parts[0], parts[1]
        status = sym_map.get(sym, "unknown")
        detail = hermes_show(tid)
        if plan_id and f"plan_id: {plan_id}" not in detail:
            continue
        m = re.search(rf"Task {re.escape(tid)}: (.+)", detail)
        title = m.group(1).strip() if m else tid
        cards[tid] = {"status": status, "title": title}
        if "gate" in title.lower() and status == "done":
            gate_done = True
    return {"cards": cards, "gate_done": gate_done}


prev = read_state()
rebuilt = not bool(prev.get("cards"))
curr = snapshot_board()
if not curr.get("gate_done"):
    curr["state_rebuilt"] = rebuilt
    write_state_atomic(curr)
    raise SystemExit(0)

done, active, blocked = board_counts(hermes_list())
now = datetime.now(timezone.utc).isoformat()
prev_cards = prev.get("cards") or {}
curr_cards = curr.get("cards") or {}

for tid, meta in curr_cards.items():
    old = prev_cards.get(tid, {})
    old_status = old.get("status")
    new_status = meta.get("status")
    title = meta.get("title", tid)
    if old_status == new_status:
        continue
    event = None
    msg = ""
    if new_status == "ready" and old_status in (None, "blocked", "todo"):
        msg = f"▶ Card start — {plan_id}\n{tid} — {title}   ({done} done · {active} active · {blocked} blocked)"
        event = {"ts": now, "type": "start", "task_id": tid, "plan_id": plan_id}
    elif new_status == "running" and old_status == "ready":
        msg = f"▶ Card running — {plan_id}\n{tid} — {title}   ({done} done · {active} active · {blocked} blocked)"
        event = {"ts": now, "type": "running", "task_id": tid, "plan_id": plan_id}
    elif new_status == "done" and old_status in ("running", "ready"):
        msg = f"✅ Card done — {plan_id}\n{tid} — {title}   ({done} done · {active} active · {blocked} blocked)"
        event = {"ts": now, "type": "done", "task_id": tid, "plan_id": plan_id}
    elif new_status in ("blocked", "crashed", "gave_up", "timed_out") and old_status == "running":
        msg = (
            f"🚨 Card re-blocked — {new_status}\n{tid} — {title}\n"
            f"Worker returned to {new_status}.   Suggested action: review card log"
        )
        event = {"ts": now, "type": "re-blocked", "task_id": tid, "plan_id": plan_id, "status": new_status}
    if event and msg:
        print(msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

curr["state_rebuilt"] = rebuilt
write_state_atomic(curr)
PY
