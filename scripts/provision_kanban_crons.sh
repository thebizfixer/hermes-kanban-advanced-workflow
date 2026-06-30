#!/usr/bin/env bash
# provision_kanban_crons.sh — Per-plan Hermes cron lifecycle for wave progression.
# IMPORTANT GOVERNANCE NOTE (hardened after bypass incidents):
# --remove for a specific PLAN_ID removes ONLY the wave crons (auto-unblock, board-keeper, lifecycle if present for that plan).
# It MUST NEVER modify .hermes/kanban-overrides/kanban-config.yaml.
# notify_lifecycle and walk_away_mode are operator-controlled settings and survive plan cleanup.
# Direct editing of the config or broad cron removal outside this script is a process violation.
#
# Usage:
#   bash scripts/provision_kanban_crons.sh --create [--plan-id ID] [--dry-run] [--json]
#   bash scripts/provision_kanban_crons.sh --remove [--plan-id ID] [--dry-run] [--json]
#   bash scripts/provision_kanban_crons.sh --check [--json]
#
# Creates kanban-auto-unblock-1m + kanban-board-keeper-3m with deliver=local, no_agent=true.
# NOT invoked at init/bootstrap — created at execute/handoff (kanban_handoff.py default profile),
# verified at decomposition, removed at cleanup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"
# shellcheck source=lib/gateway_hermes_home.sh
source "$SCRIPT_DIR/lib/gateway_hermes_home.sh"
CRON_HERMES_HOME="$KANBAN_GATEWAY_HERMES_HOME"

AUTO_UNBLOCK_NAME="kanban-auto-unblock-1m${PLAN_ID:+-$PLAN_ID}"
BOARD_KEEPER_NAME="kanban-board-keeper-3m${PLAN_ID:+-$PLAN_ID}"
LIFECYCLE_NOTIFY_NAME="kanban-lifecycle-notify-5m${PLAN_ID:+-$PLAN_ID}"
# .py launchers work around https://github.com/NousResearch/hermes-agent/issues/23404
# (bash script paths with Windows backslashes get mangled by the cron runner).
AUTO_UNBLOCK_SCRIPT="auto_unblock.py"
BOARD_KEEPER_SCRIPT="board_keeper.py"
LIFECYCLE_SCRIPT="kanban_lifecycle_notify.py"

ACTION=""
PLAN_ID=""
DRY_RUN=false
JSON_OUT=false
HEADLESS=false
WORKDIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create|--remove|--check|--clean) ACTION="${1#--}"; shift ;;
    --plan-id) PLAN_ID="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --json) JSON_OUT=true; shift ;;
    --headless) HEADLESS=true; shift ;;
    --workdir) WORKDIR="${2:-}"; shift 2 ;;
    --board) BOARD="${2:-}"; shift 2 ;;
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
REPO_ROOT="$WORKDIR"

_notify_lifecycle_enabled() {
  local cfg="$REPO_ROOT/.hermes/kanban-overrides/kanban-config.yaml"
  local val="${NOTIFY_LIFECYCLE:-}"
  if [[ -z "$val" && -f "$cfg" ]]; then
    val="$(grep -E '^[[:space:]]*notify_lifecycle:' "$cfg" 2>/dev/null | head -1 | sed 's/.*: *//; s/^"//; s/"$//' || true)"
  fi
  if [[ -z "$val" ]]; then
    val="true"
  fi
  [[ "$val" == "true" || "$val" == "1" ]]
}

if [[ "$HEADLESS" == true && "$ACTION" == "create" ]]; then
  echo "[provision_kanban_crons] headless mode — cron jobs not created."
  echo "  Manual loop (from repo root):"
  echo "    while hermes kanban list 2>/dev/null | grep -qE '⊘|●|▶'; do"
  echo "      bash ${HERMES_HOME}/scripts/${AUTO_UNBLOCK_SCRIPT} --stagger-sec \${KANBAN_UNBLOCK_STAGGER_SEC:-30}"
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
    for key in ("auto_unblock", "board_keeper", "lifecycle_notify"):
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
  local lifecycle_id="${3:-}"
  local path
  path="$(_memory_path "$PLAN_ID")" || return 0
  mkdir -p "$(dirname "$path")"
  python3 - "$path" "$auto_id" "$keeper_id" "$lifecycle_id" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
auto_id, keeper_id, lifecycle_id = sys.argv[2], sys.argv[3], sys.argv[4]
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
if lifecycle_id:
    ids["lifecycle_notify"] = lifecycle_id
data["cron_job_ids"] = ids
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
}

_cron_list() {
  HERMES_HOME="$CRON_HERMES_HOME" hermes cron list 2>/dev/null || true
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
  local deliver="${4:-local}"
  local extra_args="${5:-}"
  local existing
  existing="$(_find_job_id_by_name "$name")"
  if [[ -n "$existing" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
      echo "[provision_kanban_crons] [dry-run] would reuse job $existing ($name)"
    else
      HERMES_HOME="$CRON_HERMES_HOME" hermes cron edit "$existing" --deliver "$deliver" --no-agent --script "$script" --repeat 999 $extra_args >/dev/null 2>&1 || true
      echo "[provision_kanban_crons] reused job $existing ($name, deliver=$deliver)"
    fi
    printf '%s' "$existing"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[provision_kanban_crons] [dry-run] would create $name ($schedule, deliver=$deliver)" >&2
    printf 'dry-%s' "$name"
    return 0
  fi
  local out id
  out="$(HERMES_HOME="$CRON_HERMES_HOME" hermes cron create "$schedule" \
    --name "$name" \
    --no-agent \
    --script "$script" \
    --deliver "$deliver" \
    --repeat 999 \
    $extra_args 2>&1)" || {
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
  HERMES_HOME="$CRON_HERMES_HOME" hermes cron remove "$id" >/dev/null 2>&1 || true
  echo "[provision_kanban_crons] removed $name ($id)"
}

case "$ACTION" in
  create)
    # Clean stale plan-scoped crons from prior runs first
    if [[ -n "$PLAN_ID" && "$DRY_RUN" != true ]]; then
      bash "$0" --clean --plan-id "$PLAN_ID" ${BOARD:+--board "$BOARD"} --workdir "$WORKDIR" 2>/dev/null || true
    fi
    LIFECYCLE_DELIVER="local"
    if _notify_lifecycle_enabled; then
      LIFECYCLE_DELIVER="$(bash "$SCRIPT_DIR/lib/resolve_notify_deliver.sh" "$REPO_ROOT")"
    fi
    auto_id="$(_create_job "every 1m" "$AUTO_UNBLOCK_NAME" "$AUTO_UNBLOCK_SCRIPT" local "--workdir $WORKDIR")"
    keeper_id="$(_create_job "every 3m" "$BOARD_KEEPER_NAME" "$BOARD_KEEPER_SCRIPT" local "--workdir $WORKDIR")"
    lifecycle_id=""
    if _notify_lifecycle_enabled; then
      lifecycle_args="--workdir $WORKDIR"
      [[ -n "${BOARD:-}" ]] && lifecycle_args="$lifecycle_args --board $BOARD"
      lifecycle_id="$(_create_job "every 5m" "$LIFECYCLE_NOTIFY_NAME" "$LIFECYCLE_SCRIPT" "$LIFECYCLE_DELIVER" "$lifecycle_args")"
      if [[ -n "$PLAN_ID" && "$DRY_RUN" != true ]]; then
        mkdir -p "$REPO_ROOT/.hermes/kanban/memory"
        printf '{"plan_id":"%s","active":true}' "$PLAN_ID" > "$REPO_ROOT/.hermes/kanban/memory/${PLAN_ID}.json"
      fi
    fi
    if [[ -n "$PLAN_ID" && "$DRY_RUN" != true ]]; then
      _write_memory_ids "$auto_id" "$keeper_id" "$lifecycle_id"
    fi
    if [[ "$JSON_OUT" == true ]]; then
      printf '{"auto_unblock":"%s","board_keeper":"%s","lifecycle_notify":"%s"}\n' "$auto_id" "$keeper_id" "$lifecycle_id"
    fi
    ;;
  remove)
    # CLEANUP CONTRACT: This block removes only wave crons for the plan.
    # It does NOT touch notify_lifecycle in the overlay config.
    # See header GOVERNANCE NOTE.

    # Pre-archive audit gate: warn if final audit hasn't run.
    # The tier JSON is written by final_audit_sanity.py --tier all.
    if [[ -n "$PLAN_ID" && -n "$REPO_ROOT" ]]; then
      tier1="${REPO_ROOT}/.hermes/kanban/reports/${PLAN_ID}_audit_tier1.json"
      if [[ ! -f "$tier1" ]]; then
        echo "[provision_kanban_crons] WARN: tier1 audit JSON missing at $tier1" >&2
        echo "[provision_kanban_crons] WARN: run: python3 scripts/final_audit_sanity.py --plan-id $PLAN_ID --tier all" >&2
      fi
    fi
    stored_auto="" stored_keeper="" stored_lifecycle=""
    if [[ -n "$PLAN_ID" ]]; then
      while IFS= read -r line; do
        case "$line" in
          auto_unblock=*) stored_auto="${line#auto_unblock=}" ;;
          board_keeper=*) stored_keeper="${line#board_keeper=}" ;;
          lifecycle_notify=*) stored_lifecycle="${line#lifecycle_notify=}" ;;
        esac
      done < <(_read_memory_ids || true)
    fi
    _remove_job "$AUTO_UNBLOCK_NAME" "$stored_auto"
    _remove_job "$BOARD_KEEPER_NAME" "$stored_keeper"
    _remove_job "$LIFECYCLE_NOTIFY_NAME" "$stored_lifecycle"
  if [[ "$JSON_OUT" == true ]]; then
    echo '{"removed":true}'
  fi
  ;;
  clean)
    # Clean stale plan-scoped crons from prior runs.
    # Only removes crons whose name matches the plan_id suffix but whose
    # workdir does NOT contain the current board slug (board-scoped crons).
    # Plan-scoped crons have names like: kanban-auto-unblock-1m-{plan_id}
    # Board-scoped crons have the board slug in their workdir.
    if [[ -z "$PLAN_ID" ]]; then
      echo "[provision_kanban_crons] --clean requires --plan-id" >&2
      exit 1
    fi
    cleaned=0
    # Sanitize plan_id for name matching (same pattern as cron name suffix)
    plan_slug=$(echo "$PLAN_ID" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')
    cron_list=$(HERMES_HOME="$CRON_HERMES_HOME" hermes cron list 2>/dev/null || true)
    while IFS= read -r job_name; do
      [[ -z "$job_name" ]] && continue
      # Skip if job name doesn't contain the plan_id
      [[ "$job_name" != *"$plan_slug"* ]] && continue
      # Skip the dashboard keepalive
      [[ "$job_name" == *"dashboard"* ]] && continue
      # Check if this is a plan-scoped cron (not board-scoped)
      # Board-scoped crons have the board slug in workdir
      job_workdir=$(HERMES_HOME="$CRON_HERMES_HOME" hermes cron list 2>/dev/null | grep -A5 "Name:.*$job_name" | grep "Workdir:" | awk '{$1=""; print $0}' | xargs)
      if [[ -n "${BOARD:-}" && "$job_workdir" == *"$BOARD"* ]]; then
        echo "[provision_kanban_crons] [clean] skipping board-scoped: $job_name (workdir=$job_workdir)"
        continue
      fi
      # Remove stale plan-scoped cron
      if [[ "$DRY_RUN" == true ]]; then
        echo "[provision_kanban_crons] [dry-run] would remove stale cron: $job_name"
      else
        jid=$(HERMES_HOME="$CRON_HERMES_HOME" hermes cron list 2>/dev/null | grep -B2 "Name:.*$job_name" | grep "^  ID:" | awk '{print $2}')
        if [[ -n "$jid" ]]; then
          HERMES_HOME="$CRON_HERMES_HOME" hermes cron remove "$jid" 2>/dev/null && {
            echo "[provision_kanban_crons] [clean] removed stale cron: $job_name ($jid)"
            cleaned=$((cleaned + 1))
          }
        fi
      fi
    done < <(echo "$cron_list" | grep "Name:" | sed 's/.*Name: *//')
    echo "[provision_kanban_crons] [clean] removed $cleaned stale plan-scoped cron(s)"
  ;;
  check)
    issues=0
  if ! command -v hermes >/dev/null 2>&1; then
      echo "[provision_kanban_crons] FAIL: hermes not on PATH" >&2
      exit 1
    fi
    for script in "$AUTO_UNBLOCK_SCRIPT" "$BOARD_KEEPER_SCRIPT"; do
      if [[ ! -x "${CRON_HERMES_HOME}/scripts/${script}" ]]; then
        echo "[provision_kanban_crons] FAIL: ${CRON_HERMES_HOME}/scripts/${script} missing or not executable" >&2
        issues=$((issues + 1))
      fi
    done
    if _notify_lifecycle_enabled; then
      if [[ ! -x "${CRON_HERMES_HOME}/scripts/${LIFECYCLE_SCRIPT}" ]]; then
        echo "[provision_kanban_crons] FAIL: ${LIFECYCLE_SCRIPT} missing (notify_lifecycle enabled)" >&2
        issues=$((issues + 1))
      fi
    fi
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
    if _notify_lifecycle_enabled; then
      id="$(_find_job_id_by_name "$LIFECYCLE_NOTIFY_NAME")"
      if [[ -z "$id" ]]; then
        echo "[provision_kanban_crons] FAIL: cron job not found: $LIFECYCLE_NOTIFY_NAME (notify_lifecycle enabled)" >&2
        issues=$((issues + 1))
      else
        block="$(_cron_list | awk -v id="$id" '
          $0 ~ "^  " id " " { found=1 }
          found && $0 ~ "^  [a-f0-9]+ \\[" && $0 !~ id { exit }
          found { print }
        ')"
        if ! echo "$block" | grep -q '\[active\]'; then
          echo "[provision_kanban_crons] FAIL: $LIFECYCLE_NOTIFY_NAME ($id) not active" >&2
          issues=$((issues + 1))
        fi
        if echo "$block" | grep -qi 'Deliver:.*local'; then
          echo "[provision_kanban_crons] FAIL: $LIFECYCLE_NOTIFY_NAME deliver is local (expected home channel)" >&2
          issues=$((issues + 1))
        fi
        resolved="$(bash "$SCRIPT_DIR/lib/resolve_notify_deliver.sh" "$REPO_ROOT" 2>/dev/null || echo unknown)"
        echo "[provision_kanban_crons] lifecycle deliver resolved: $resolved"
      fi
    fi
    if kanban_is_profile_scoped_hermes_home; then
      echo "[provision_kanban_crons] WARN: session HERMES_HOME is profile-scoped ($HERMES_HOME); cron ops use gateway store ($CRON_HERMES_HOME)" >&2
    fi
    if ! _gateway_running; then
      echo "[provision_kanban_crons] WARN: gateway not running — crons will not tick until hermes gateway start" >&2
    fi
    if [[ "$issues" -gt 0 ]]; then
      exit 1
    fi
    echo "[provision_kanban_crons] OK: wave crons active in gateway store ($CRON_HERMES_HOME, deliver=local, no-agent)"
    if _notify_lifecycle_enabled; then
      echo "[provision_kanban_crons] OK: lifecycle cron active with home-channel deliver"
    fi
    if [[ "$JSON_OUT" == true ]]; then
      echo '{"ok":true}'
    fi
    ;;
esac
