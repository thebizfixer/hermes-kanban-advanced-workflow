#!/usr/bin/env bash
# provision_kanban_crons.sh — Per-plan Hermes cron lifecycle for wave progression.
#
# Usage:
#   bash scripts/provision_kanban_crons.sh --create [--plan-id ID] [--dry-run] [--json]
#   bash scripts/provision_kanban_crons.sh --remove [--plan-id ID] [--dry-run] [--json]
#   bash scripts/provision_kanban_crons.sh --check [--json]
#
# Creates kanban-auto-unblock-1m + kanban-board-keeper-3m with deliver=local, no_agent=true.
# NOT invoked at init/bootstrap — only at decomposition (create) and cleanup (remove).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"

AUTO_UNBLOCK_NAME="kanban-auto-unblock-1m"
BOARD_KEEPER_NAME="kanban-board-keeper-3m"
AUTO_UNBLOCK_SCRIPT="auto_unblock.sh"
BOARD_KEEPER_SCRIPT="board_keeper.sh"

ACTION=""
PLAN_ID=""
DRY_RUN=false
JSON_OUT=false
HEADLESS=false
WORKDIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create|--remove|--check) ACTION="${1#--}"; shift ;;
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --json) JSON_OUT=true; shift ;;
    --headless) HEADLESS=true; shift ;;
    --workdir) WORKDIR="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *) echo "[provision_kanban_crons] unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ACTION" ]]; then
  echo "[provision_kanban_crons] specify --create, --remove, or --check" >&2
  exit 2
fi

if [[ -z "$WORKDIR" ]]; then
  WORKDIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

if [[ "$HEADLESS" == true && "$ACTION" == "create" ]]; then
  echo "[provision_kanban_crons] headless mode — cron jobs not created."
  echo "  Manual loop (from repo root):"
  echo "    while hermes kanban list 2>/dev/null | grep -qE '⊘|●|▶'; do"
  echo "      bash ${HERMES_HOME}/scripts/auto_unblock.sh --stagger-sec \${KANBAN_UNBLOCK_STAGGER_SEC:-30}"
  echo "      sleep 60"
  echo "    done"
  exit 0
fi

_memory_path() {
  local pid="${1:-}"
  [[ -z "$pid" ]] && return 1
  printf '%s/kanban/memory/%s.json' "$HERMES_HOME" "$pid"
}

_read_memory_ids() {
  local path
  path="$(_memory_path "$PLAN_ID")" || return 1
  [[ -f "$path" ]] || return 1
  python3 - "$path" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    ids = data.get("cron_job_ids") or {}
    for key in ("auto_unblock", "board_keeper"):
        val = ids.get(key, "")
        if val:
            print(f"{key}={val}")
except Exception:
    pass
PY
}

_write_memory_ids() {
  local auto_id="$1"
  local keeper_id="$2"
  local path
  path="$(_memory_path "$PLAN_ID")" || return 0
  mkdir -p "$(dirname "$path")"
  python3 - "$path" "$auto_id" "$keeper_id" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
auto_id, keeper_id = sys.argv[2], sys.argv[3]
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
ids = data.get("cron_job_ids") or {}
if not isinstance(ids, dict):
    ids = {}
if auto_id:
    ids["auto_unblock"] = auto_id
if keeper_id:
    ids["board_keeper"] = keeper_id
data["cron_job_ids"] = ids
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
}

_cron_list() {
  hermes cron list 2>/dev/null || true
}

_find_job_id_by_name() {
  local name="$1"
  _cron_list | awk -v n="$name" '
    $0 ~ "^  [a-f0-9]+ \\[" { id=$1 }
    $0 ~ "^    Name:" && index($0, n) { print id; exit }
  '
}

_gateway_running() {
  if hermes cron status 2>/dev/null | grep -qiE 'running|active'; then
    return 0
  fi
  if hermes gateway status 2>/dev/null | grep -qiE 'running|active'; then
    return 0
  fi
  return 1
}

_create_job() {
  local schedule="$1"
  local name="$2"
  local script="$3"
  local workdir_args=()
  [[ -n "$WORKDIR" ]] && workdir_args=(--workdir "$WORKDIR")
  local existing
  existing="$(_find_job_id_by_name "$name")"
  if [[ -n "$existing" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
      echo "[provision_kanban_crons] [dry-run] would reuse job $existing ($name)"
    else
      hermes cron edit "$existing" --deliver local --no-agent --script "$script" --repeat 999 "${workdir_args[@]}" >/dev/null 2>&1 || true
      echo "[provision_kanban_crons] reused job $existing ($name)"
    fi
    printf '%s' "$existing"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[provision_kanban_crons] [dry-run] would create $name ($schedule)" >&2
    printf 'dry-%s' "$name"
    return 0
  fi
  local out id
  out="$(hermes cron create "$schedule" \
    --name "$name" \
    --no-agent \
    --script "$script" \
    --deliver local \
    --repeat 999 \
    "${workdir_args[@]}" 2>&1)" || {
    echo "[provision_kanban_crons] create failed for $name: $out" >&2
    return 1
  }
  id="$(echo "$out" | sed -n 's/^Created job: //p' | head -1)"
  if [[ -z "$id" ]]; then
    id="$(_find_job_id_by_name "$name")"
  fi
  if [[ -z "$id" ]]; then
    echo "[provision_kanban_crons] could not resolve job id for $name" >&2
    return 1
  fi
  echo "[provision_kanban_crons] created $name → $id" >&2
  printf '%s' "$id"
}

_remove_job() {
  local name="$1"
  local stored_id="${2:-}"
  local id="$stored_id"
  if [[ -z "$id" ]]; then
    id="$(_find_job_id_by_name "$name")"
  fi
  if [[ -z "$id" ]]; then
    echo "[provision_kanban_crons] no job to remove: $name"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[provision_kanban_crons] [dry-run] would remove $name ($id)"
    return 0
  fi
  hermes cron remove "$id" >/dev/null 2>&1 || true
  echo "[provision_kanban_crons] removed $name ($id)"
}

case "$ACTION" in
  create)
    auto_id="$(_create_job "every 1m" "$AUTO_UNBLOCK_NAME" "$AUTO_UNBLOCK_SCRIPT")"
    keeper_id="$(_create_job "every 3m" "$BOARD_KEEPER_NAME" "$BOARD_KEEPER_SCRIPT")"
    if [[ -n "$PLAN_ID" && "$DRY_RUN" != true ]]; then
      _write_memory_ids "$auto_id" "$keeper_id"
    fi
    if [[ "$JSON_OUT" == true ]]; then
      printf '{"auto_unblock":"%s","board_keeper":"%s"}\n' "$auto_id" "$keeper_id"
    fi
    ;;
  remove)
    stored_auto="" stored_keeper=""
    if [[ -n "$PLAN_ID" ]]; then
      while IFS= read -r line; do
        case "$line" in
          auto_unblock=*) stored_auto="${line#auto_unblock=}" ;;
          board_keeper=*) stored_keeper="${line#board_keeper=}" ;;
        esac
      done < <(_read_memory_ids || true)
    fi
    _remove_job "$AUTO_UNBLOCK_NAME" "$stored_auto"
    _remove_job "$BOARD_KEEPER_NAME" "$stored_keeper"
  if [[ "$JSON_OUT" == true ]]; then
      echo '{"removed":true}'
    fi
    ;;
  check)
    issues=0
  if ! command -v hermes >/dev/null 2>&1; then
      echo "[provision_kanban_crons] FAIL: hermes not on PATH" >&2
      exit 1
    fi
    for script in "$AUTO_UNBLOCK_SCRIPT" "$BOARD_KEEPER_SCRIPT"; do
      if [[ ! -x "${HERMES_HOME}/scripts/${script}" ]]; then
        echo "[provision_kanban_crons] FAIL: ${HERMES_HOME}/scripts/${script} missing or not executable" >&2
        issues=$((issues + 1))
      fi
    done
    for name in "$AUTO_UNBLOCK_NAME" "$BOARD_KEEPER_NAME"; do
      id="$(_find_job_id_by_name "$name")"
      if [[ -z "$id" ]]; then
        echo "[provision_kanban_crons] FAIL: cron job not found: $name" >&2
        issues=$((issues + 1))
        continue
      fi
      block="$(_cron_list | awk -v id="$id" '
        $0 ~ "^  " id " " { found=1 }
        found && $0 ~ "^  [a-f0-9]+ \\[" && $0 !~ id { exit }
        found { print }
      ')"
      if ! echo "$block" | grep -q '\[active\]'; then
        echo "[provision_kanban_crons] FAIL: $name ($id) not active" >&2
        issues=$((issues + 1))
      fi
      if ! echo "$block" | grep -qi 'Deliver:.*local'; then
        echo "[provision_kanban_crons] FAIL: $name deliver is not local" >&2
        issues=$((issues + 1))
      fi
      if ! echo "$block" | grep -qi 'no-agent'; then
        echo "[provision_kanban_crons] FAIL: $name is not no-agent mode" >&2
        issues=$((issues + 1))
      fi
    done
    if ! _gateway_running; then
      echo "[provision_kanban_crons] WARN: gateway not running — crons will not tick until hermes gateway start" >&2
    fi
    if [[ "$issues" -gt 0 ]]; then
      exit 1
    fi
    echo "[provision_kanban_crons] OK: wave crons active (deliver=local, no-agent)"
    if [[ "$JSON_OUT" == true ]]; then
      echo '{"ok":true}'
    fi
    ;;
esac
