#!/usr/bin/env bash
# Kanban preflight — environment validation before decomposition.
# Sources repo .env, runs checks from kanban-preflight skill checklist,
# prints JSON to stdout. Exit 1 on blocking failures; exit 0 on pass or degraded-only.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"

CHECK_TIMEOUT="${CHECK_TIMEOUT:-5}"
PREFLIGHT_MEMORY_MIN_MB="${PREFLIGHT_MEMORY_MIN_MB:-1024}"
PREFLIGHT_MEMORY_WARN_MB="${PREFLIGHT_MEMORY_WARN_MB:-2048}"
PREFLIGHT_API_URL="${PREFLIGHT_API_URL:-http://127.0.0.1:8000/healthz}"
PREFLIGHT_PROFILES="${PREFLIGHT_PROFILES:-kanban-advanced-worker,kanban-advanced-orchestrator}"
PREFLIGHT_REQUIRED_SECRETS="${PREFLIGHT_REQUIRED_SECRETS:-}"
WORKER_PROFILE="${WORKER_PROFILE:-kanban-advanced-worker}"

# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

# shellcheck source=lib/kanban_db_path.sh
source "$SCRIPT_DIR/lib/kanban_db_path.sh" 2>/dev/null || true

REPO_ROOT="$(resolve_project_root "$SCRIPT_DIR")"
cd "$REPO_ROOT"

OVERLAY_CONFIG="$REPO_ROOT/.hermes/kanban-overrides/kanban-config.yaml"
if [[ -f "$OVERLAY_CONFIG" ]]; then
  _pf="$(grep -E '^preflight_profiles:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^preflight_profiles: *//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')"
  [[ -n "$_pf" ]] && PREFLIGHT_PROFILES="$_pf" || true
  _wp="$(grep -E '^worker_profile:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^worker_profile: *//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')"
  [[ -n "$_wp" ]] && WORKER_PROFILE="$_wp" || true
  _rs="$(grep -E '^required_secrets:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^required_secrets: *//; s/"//g; s/'"'"'//g')" || true
  [[ -n "$_rs" ]] && PREFLIGHT_REQUIRED_SECRETS="$_rs" || true
  _api="$(grep -E '^preflight_api_url:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^preflight_api_url: *//; s/^"//; s/"$//')" || true
  [[ -n "$_api" ]] && PREFLIGHT_API_URL="$_api" || true
fi

if [[ -f "$REPO_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

ENVIRONMENT="${ENVIRONMENT:-local}"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

declare -a CHECK_JSON_LINES=()
BLOCKING_FAILURES=0
DEGRADED_WARNINGS=0

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

record_check() {
  local id="$1"
  local status="$2"
  local severity="$3"
  local message="$4"

  if [[ "$status" == "fail" && "$severity" == "blocking" ]]; then
    BLOCKING_FAILURES=$((BLOCKING_FAILURES + 1))
  elif [[ "$status" == "degraded" || ("$status" == "fail" && "$severity" == "degraded") ]]; then
    DEGRADED_WARNINGS=$((DEGRADED_WARNINGS + 1))
  fi

  local msg_json
  msg_json="$(printf '%s' "$message" | json_escape)"
  CHECK_JSON_LINES+=(
    "$(printf '{\"id\":%s,\"status\":%s,\"severity\":%s,\"message\":%s}' \
      "$(printf '%s' "$id" | json_escape)" \
      "$(printf '%s' "$status" | json_escape)" \
      "$(printf '%s' "$severity" | json_escape)" \
      "$msg_json")"
  )
}

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

check_memory_budget() {
  local avail_mb="0"

  if [[ "${PREFLIGHT_SKIP_MEMORY_BUDGET:-}" == "1" ]]; then
    record_check "memory_budget" "pass" "blocking" \
      "Skipped by PREFLIGHT_SKIP_MEMORY_BUDGET=1 (audit-noted override)"
    return
  fi

  if [[ -r /proc/meminfo ]]; then
    # Linux / WSL2
    local avail_kb
    avail_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
    avail_mb=$((avail_kb / 1024))
  elif command -v free >/dev/null 2>&1; then
    # Linux fallback (GNU coreutils, Git Bash on Windows)
    avail_mb="$(free -m | awk '/^Mem:/ {print $7}')"
    avail_mb="${avail_mb:-0}"
  elif command -v vm_stat >/dev/null 2>&1; then
    # macOS: estimate available memory from vm_stat page counts
    # free + speculative + inactive are all reclaimable by the kernel
    local page_size free_pages speculative inactive
    page_size=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
    free_pages=$(vm_stat | awk '/^Pages free:/ {gsub(/\./, "", $NF); print $NF+0}')
    speculative=$(vm_stat | awk '/^Pages speculative:/ {gsub(/\./, "", $NF); print $NF+0}')
    inactive=$(vm_stat | awk '/^Pages inactive:/ {gsub(/\./, "", $NF); print $NF+0}')
    free_pages=${free_pages:-0}
    speculative=${speculative:-0}
    inactive=${inactive:-0}
    avail_mb=$(( (free_pages + speculative + inactive) * page_size / 1024 / 1024 ))
  elif [[ "$(uname -s 2>/dev/null)" == MINGW* ]] || [[ "$(uname -s 2>/dev/null)" == MSYS* ]]; then
    # Windows Git Bash / MSYS: try systeminfo first, fall back to PowerShell
    local avail_str
    avail_str=$(systeminfo 2>/dev/null | awk -F': *' '/Available Physical Memory/ {gsub(/,/,""); print $2}' | tr -d '\r')
    if [[ -z "$avail_str" ]] && command -v powershell >/dev/null 2>&1; then
      local free_kb
      free_kb=$(powershell -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory" 2>/dev/null)
      avail_mb=$(( free_kb / 1024 ))
    else
      avail_mb="${avail_str:-0}"
    fi
  fi

  if [[ "$avail_mb" -lt "$PREFLIGHT_MEMORY_MIN_MB" ]]; then
    record_check "memory_budget" "fail" "blocking" \
      "Available memory ${avail_mb}MB is below minimum ${PREFLIGHT_MEMORY_MIN_MB}MB"
  elif [[ "$avail_mb" -lt "$PREFLIGHT_MEMORY_WARN_MB" ]]; then
    record_check "memory_budget" "degraded" "degraded" \
      "Available memory ${avail_mb}MB is below recommended ${PREFLIGHT_MEMORY_WARN_MB}MB"
  else
    record_check "memory_budget" "pass" "blocking" \
      "Available memory ${avail_mb}MB meets budget (${PREFLIGHT_MEMORY_WARN_MB}MB recommended)"
  fi
}

check_secret_availability() {
  local missing=()
  local secret
  IFS=',' read -r -a required <<< "$PREFLIGHT_REQUIRED_SECRETS"
  for secret in "${required[@]}"; do
    secret="$(printf '%s' "$secret" | tr -d '[:space:]"'\''')"
    [[ -z "$secret" ]] && continue
    if [[ -z "${!secret:-}" ]]; then
      missing+=("$secret")
    fi
  done

  if [[ "$ENVIRONMENT" == "production" && -z "${SECRET_KEY:-}" ]]; then
    missing+=("SECRET_KEY")
  fi

  if [[ -z "${PREFLIGHT_REQUIRED_SECRETS// /}" ]]; then
    record_check "secret_availability" "pass" "blocking" \
      "No required_secrets configured in kanban-config.yaml (skipped)"
  elif ((${#missing[@]} > 0)); then
    local joined
    joined="$(IFS=,; printf '%s' "${missing[*]}")"
    record_check "secret_availability" "fail" "blocking" \
      "Missing required secrets: ${joined}"
  else
    record_check "secret_availability" "pass" "blocking" \
      "Required secrets present (${PREFLIGHT_REQUIRED_SECRETS})"
  fi
}

check_api_reachability() {
  if [[ -z "${PREFLIGHT_SKIP_API:-}" ]]; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$CHECK_TIMEOUT" "$PREFLIGHT_API_URL" 2>/dev/null || printf '000')"
    if [[ "$code" =~ ^[23] ]]; then
      record_check "api_reachability" "pass" "degraded" \
        "API reachable at ${PREFLIGHT_API_URL} (HTTP ${code})"
    else
      record_check "api_reachability" "degraded" "degraded" \
        "API unreachable at ${PREFLIGHT_API_URL} (HTTP ${code})"
    fi
  else
    record_check "api_reachability" "pass" "degraded" \
      "Skipped (PREFLIGHT_SKIP_API set)"
  fi
}

check_gateway_health() {
  if ! command -v hermes >/dev/null 2>&1; then
    record_check "gateway_health" "fail" "blocking" \
      "hermes CLI not found on PATH"
    return
  fi

  local status_out=""
  if status_out="$(run_with_timeout "$CHECK_TIMEOUT" hermes gateway status 2>&1)"; then
    if printf '%s' "$status_out" | grep -qiE 'running|active|online|listening'; then
      record_check "gateway_health" "pass" "blocking" "Hermes gateway is running"
    else
      record_check "gateway_health" "pass" "blocking" \
        "hermes gateway status succeeded"
    fi
  else
    record_check "gateway_health" "fail" "blocking" \
      "Hermes gateway is not running (start: hermes gateway run)"
  fi
}

check_profile_availability() {
  local issues=()
  local profile
  local profiles_out=""

  if ! command -v hermes >/dev/null 2>&1; then
    record_check "profile_availability" "fail" "blocking" \
      "hermes CLI not found on PATH"
    return
  fi

  profiles_out="$(run_with_timeout "$CHECK_TIMEOUT" hermes profile list 2>/dev/null || true)"
  IFS=',' read -r -a required_profiles <<< "$PREFLIGHT_PROFILES"
  for profile in "${required_profiles[@]}"; do
    profile="$(printf '%s' "$profile" | tr -d '[:space:]"'\''')"
    [[ -z "$profile" ]] && continue
    if ! printf '%s' "$profiles_out" | grep -q "$profile"; then
      issues+=("missing profile: ${profile}")
    fi
  done

  # Coding-agent CLI auth is verified by check_coding_agent_cli_reachability()
  # (headless smoke via check_coding_agent_cli.py). Do NOT use `agent status` here —
  # it reports OAuth file presence, not execution capability.
  if ! command -v agent >/dev/null 2>&1; then
    issues+=("agent binary not found")
  elif ! run_with_timeout "$CHECK_TIMEOUT" agent --version >/dev/null 2>&1; then
    issues+=("agent --version failed")
  fi

  local soul_path="${HERMES_HOME}/profiles/${WORKER_PROFILE}/SOUL.md"
  if [[ -f "$soul_path" ]] && grep -qE '%3C|%3E' "$soul_path" 2>/dev/null; then
    issues+=("SOUL.md corruption detected")
  fi

  if ((${#issues[@]} > 0)); then
    local joined
    joined="$(IFS='; '; printf '%s' "${issues[*]}")"
    record_check "profile_availability" "fail" "blocking" "$joined"
  else
    record_check "profile_availability" "pass" "blocking" \
      "Profiles (${PREFLIGHT_PROFILES}) present; agent binary on PATH"
  fi
}

check_coding_agent_cli_reachability() {
  # Hermes profile model_reachability pings the LLM backend for dispatch profiles.
  # Workers dispatch a separate coding-agent CLI (Cursor agent, Claude, Codex, …).
  # This check must pass before decomposition — dashboard green dot is not enough.
  local probe_timeout="${PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT:-15}"
  local binary="${KANBAN_CODING_AGENT:-}"
  local out="" rc=0

  if [[ "${PREFLIGHT_SKIP_CODING_AGENT_CLI:-}" == "1" ]]; then
    record_check "coding_agent_cli_reachability" "pass" "blocking" \
      "Skipped by PREFLIGHT_SKIP_CODING_AGENT_CLI=1 (audit-noted override)"
    return
  fi

  if [[ -f "$OVERLAY_CONFIG" ]]; then
    _cab="$(grep -E '^coding_agent_binary:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^coding_agent_binary: *//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')"
    [[ -n "$_cab" ]] && binary="$_cab" || true
  fi
  binary="${binary:-agent}"

  if ! command -v "$binary" >/dev/null 2>&1; then
    record_check "coding_agent_cli_reachability" "fail" "blocking" \
      "Coding agent binary '${binary}' not on PATH — install CLI or fix coding_agent_binary"
    return
  fi

  if [[ -z "${HOME:-}" ]]; then
    record_check "coding_agent_cli_reachability" "fail" "blocking" \
      "HOME is unset — coding-agent CLIs cannot load OAuth (set HOME in .env or gateway systemd unit)"
    return
  fi

  local wall_timeout=$((probe_timeout + 5))

  out="$(run_with_timeout "$wall_timeout" sh -c \
    "cd \"${REPO_ROOT}\" && PYTHONPATH=\"${SCRIPT_DIR}/..:${REPO_ROOT}\" python3 \"${SCRIPT_DIR}/check_coding_agent_cli.py\" --timeout \"${probe_timeout}\"" \
    2>&1)" \
    || rc=$?

  if [[ $rc -eq 0 ]]; then
    record_check "coding_agent_cli_reachability" "pass" "blocking" \
      "Coding agent CLI (${binary}) headless smoke passed"
  elif [[ $rc -eq 2 ]]; then
    record_check "coding_agent_cli_reachability" "fail" "blocking" \
      "Coding agent binary '${binary}' not on PATH"
  elif [[ $rc -eq 124 ]]; then
    record_check "coding_agent_cli_reachability" "fail" "blocking" \
      "Coding agent CLI (${binary}) smoke timed out after ${probe_timeout}s — fix auth or export PREFLIGHT_SKIP_CODING_AGENT_CLI=1 (audit-noted override)"
  else
    record_check "coding_agent_cli_reachability" "fail" "blocking" \
      "${out:-Coding agent CLI (${binary}) smoke failed — see docs: wiki/troubleshooting.md § Cursor OAuth}"
  fi
}

check_model_reachability() {
  # For each profile in PREFLIGHT_PROFILES, send a minimal chat query to confirm
  # the model is reachable. This catches typos in model names and truly expired
  # tokens — issues that `hermes auth status` misses for proxy-routed providers
  # (e.g. stepfun via Nous Portal reporting "logged out" when the model is live).
  # Uses a 15-second timeout; no --yolo required since "say ok" never triggers tools.
  local MODEL_PING_TIMEOUT="${PREFLIGHT_MODEL_PING_TIMEOUT:-15}"
  local issues=()
  local warnings=()

  if ! command -v hermes >/dev/null 2>&1; then
    record_check "model_reachability" "degraded" "degraded" \
      "hermes not on PATH — skipping model reachability check"
    return
  fi

  IFS=',' read -r -a _mr_profiles <<< "$PREFLIGHT_PROFILES"
  for _mr_profile in "${_mr_profiles[@]}"; do
    _mr_profile="$(printf '%s' "$_mr_profile" | tr -d '[:space:]"'\''')"
    [[ -z "$_mr_profile" ]] && continue

    local _mr_out="" _mr_rc=0
    _mr_out="$(run_with_timeout "$MODEL_PING_TIMEOUT" \
      hermes -p "$_mr_profile" chat -q "say ok" 2>&1)" \
      || _mr_rc=$?

    local _mr_lower
    _mr_lower="$(printf '%s' "$_mr_out" | tr '[:upper:]' '[:lower:]')"

    if [[ $_mr_rc -eq 0 ]]; then
      : # model responded within timeout — pass
    elif printf '%s' "$_mr_lower" | grep -qE \
        'model not found|no such model|unknown model|invalid model|does not exist|not available'; then
      issues+=("${_mr_profile}: model name invalid or not found — check profile config")
    elif printf '%s' "$_mr_lower" | grep -qE \
        'authentication|unauthorized|401|403|token.*expired|api key'; then
      issues+=("${_mr_profile}: authentication failed — run: hermes auth add <provider>")
    elif [[ $_mr_rc -eq 124 ]]; then
      # exit 124 = timeout(1) timed out
      warnings+=("${_mr_profile}: model ping timed out after ${MODEL_PING_TIMEOUT}s — may be slow or overloaded")
    else
      warnings+=("${_mr_profile}: model ping failed (rc=${_mr_rc}) — verify manually")
    fi
  done

  if ((${#issues[@]} > 0)); then
    local _mr_joined
    _mr_joined="$(IFS='; '; printf '%s' "${issues[*]}")"
    record_check "model_reachability" "fail" "blocking" "$_mr_joined"
  elif ((${#warnings[@]} > 0)); then
    local _mr_joined
    _mr_joined="$(IFS='; '; printf '%s' "${warnings[*]}")"
    record_check "model_reachability" "degraded" "degraded" "$_mr_joined"
  else
    record_check "model_reachability" "pass" "blocking" \
      "Model ping passed for profiles (${PREFLIGHT_PROFILES})"
  fi
}

check_environment_parity() {
  local issues=()
  local warnings=()

  case "$ENVIRONMENT" in
    local|dev|production) ;;
    *)
      issues+=("ENVIRONMENT=${ENVIRONMENT} is not local, dev, or production")
      ;;
  esac

  _allowed_envs="$(grep -E '^allowed_environments:' "$OVERLAY_CONFIG" 2>/dev/null | head -1 | sed 's/^allowed_environments: *//; s/"//g; s/'"'"'//g' || true)"
  if [[ -n "$_allowed_envs" ]]; then
    IFS=',' read -ra _env_list <<< "$_allowed_envs"
    _env_ok=false
    for _e in "${_env_list[@]}"; do
      _e="${_e// /}"
      [[ "$_e" == "$ENVIRONMENT" ]] && _env_ok=true
    done
    if [[ "$_env_ok" == false ]]; then
      issues+=("ENVIRONMENT=${ENVIRONMENT} not in allowed_environments (${_allowed_envs})")
    fi
  fi

  if [[ "$ENVIRONMENT" == "production" && -z "${SECRET_KEY:-}" ]]; then
    issues+=("SECRET_KEY required when ENVIRONMENT=production")
  fi

  if [[ "$ENVIRONMENT" == "production" && "${PUBLIC_APP_URL:-}" == *localhost* ]]; then
    warnings+=("PUBLIC_APP_URL points at localhost in production")
  fi

  if ((${#issues[@]} > 0)); then
    local joined
    joined="$(IFS='; '; printf '%s' "${issues[*]}")"
    record_check "environment_parity" "fail" "blocking" "$joined"
  elif ((${#warnings[@]} > 0)); then
    local joined
    joined="$(IFS='; '; printf '%s' "${warnings[*]}")"
    record_check "environment_parity" "degraded" "degraded" "$joined"
  else
    record_check "environment_parity" "pass" "blocking" \
      "ENVIRONMENT=${ENVIRONMENT} parity checks passed"
  fi
}

check_filesystem_coherence() {
  # Block if REPO_ROOT is on a cross-mount filesystem (WSL DrvFs, NFS, FUSE, CIFS, etc.)
  # Override: PREFLIGHT_ALLOWED_FS_TYPES (comma-separated whitelist)
  # Emergency skip: PREFLIGHT_SKIP_FS_CHECK=1 (audit-noted)

  if [[ "${PREFLIGHT_SKIP_FS_CHECK:-}" == "1" ]]; then
    record_check "filesystem_coherence" "pass" "blocking" \
      "Skipped by PREFLIGHT_SKIP_FS_CHECK=1 (audit-noted override)"
    return
  fi

  # ── Path-prefix guard ──────────────────────────────────────────
  local path_warning=""
  case "$REPO_ROOT" in
    /mnt/*)
      if [[ $(uname -r) =~ (WSL|Microsoft) ]]; then
        path_warning="WSL DrvFs mount detected at $REPO_ROOT (cross-mount: /mnt/ → Windows NTFS). Clone to a native WSL path (e.g., ~/projects/)."
      else
        path_warning="Path starts with /mnt/ at $REPO_ROOT (possible cross-mount). Verify filesystem type."
      fi
      ;;
    /net/*)
      path_warning="Autofs/NFS mount detected at $REPO_ROOT (cross-mount: /net/). Clone to a local native filesystem."
      ;;
    /Volumes/*)
      path_warning="External/mounted volume at $REPO_ROOT (cross-mount: /Volumes/). Clone to the internal disk."
      ;;
  esac

  if [[ -n "$path_warning" ]]; then
    record_check "filesystem_coherence" "fail" "blocking" "$path_warning"
    return
  fi

  # ── Filesystem type guard ──────────────────────────────────────
  local fs_type
  # Linux/WSL2: df -T prints type in column 2.
  # macOS BSD df: -T is not a type flag — use diskutil instead.
  # Git Bash/Windows: df -T works via MSYS2 coreutils.
  fs_type=$(df -T "$REPO_ROOT" 2>/dev/null | awk 'NR==2 {print $2}')
  if [[ -z "$fs_type" ]] && command -v diskutil >/dev/null 2>&1; then
    # macOS fallback: extract filesystem personality from diskutil
    fs_type=$(diskutil info "$REPO_ROOT" 2>/dev/null \
      | awk '/File System Personality:/ {print $NF}' \
      | tr '[:upper:]' '[:lower:]')
  fi

  if [[ -z "$fs_type" ]]; then
    record_check "filesystem_coherence" "degraded" "degraded" \
      "Could not determine filesystem type for $REPO_ROOT (df -T and diskutil both failed). Cannot validate coherence."
    return
  fi

  local allowed_types="${PREFLIGHT_ALLOWED_FS_TYPES:-}"
  if [[ -n "$allowed_types" ]]; then
    local allowed
    IFS=',' read -r -a allowed <<< "$allowed_types"
    local found=false
    for at in "${allowed[@]}"; do
      at=$(printf '%s' "$at" | tr -d '[:space:]')
      [[ "$fs_type" == "$at" ]] && found=true && break
    done
    if [[ "$found" == "true" ]]; then
      record_check "filesystem_coherence" "pass" "blocking" \
        "Filesystem type $fs_type is in PREFLIGHT_ALLOWED_FS_TYPES ($allowed_types)"
    else
      record_check "filesystem_coherence" "fail" "blocking" \
        "Filesystem type $fs_type at $REPO_ROOT is not in PREFLIGHT_ALLOWED_FS_TYPES ($allowed_types)"
    fi
  else
    local blocked_types="9p nfs nfs4 fuse fuseblk cifs smbfs sshfs"
    local blocked=false
    for bt in $blocked_types; do
      if [[ "$fs_type" == "$bt" ]]; then
        blocked=true
        break
      fi
    done

    if [[ "$blocked" == "true" ]]; then
      record_check "filesystem_coherence" "fail" "blocking" \
        "Filesystem type $fs_type at $REPO_ROOT is a cross-mount/network filesystem. Clone to a native filesystem (ext4, xfs, apfs, btrfs). Override with PREFLIGHT_ALLOWED_FS_TYPES if this is intentional."
    else
      record_check "filesystem_coherence" "pass" "blocking" \
        "Filesystem type $fs_type at $REPO_ROOT is native (not blocked)"
    fi
  fi
}

check_kanban_db_integrity() {
  if [[ "${PREFLIGHT_SKIP_DB_CHECK:-}" == "1" ]]; then
    record_check "kanban_db_integrity" "pass" "blocking" \
      "Skipped by PREFLIGHT_SKIP_DB_CHECK=1 (audit-noted override)"
    return
  fi
  local db="${KANBAN_DB_PATH:-${HERMES_HOME}/kanban.db}"
  local lock="${db}.init.lock"
  if [[ -f "$lock" ]]; then
    rm -f "$lock" 2>/dev/null || true
  fi
  if [[ ! -f "$db" ]]; then
    record_check "kanban_db_integrity" "degraded" "degraded" \
      "kanban.db not found at $db (gateway may create on first run)"
    return
  fi
  if python3 -c "import sqlite3, os; db_path=os.environ.get('KANBAN_DB_PATH', os.path.join(os.environ.get('HERMES_HOME',''),'kanban.db')); c=sqlite3.connect(db_path); r=c.execute('PRAGMA integrity_check').fetchone()[0]; assert r=='ok', r; c.close()"; then
    record_check "kanban_db_integrity" "pass" "blocking" "kanban.db integrity ok at $db"
  else
    record_check "kanban_db_integrity" "fail" "blocking" "kanban.db integrity check failed at $db"
  fi
}

check_token_log() {
  local token_path="${KANBAN_TOKEN_LOG:-$HERMES_HOME/kanban/tokens.jsonl}"
  local token_dir
  token_dir="$(dirname "$token_path")"
  
  if [[ -w "$token_path" ]]; then
    record_check "token_log" "pass" "degraded" \
      "Token log writable at $token_path"
  elif [[ -d "$token_dir" && -w "$token_dir" ]]; then
    record_check "token_log" "pass" "degraded" \
      "Token log directory exists and is writable at $token_dir (file will be created)"
  elif [[ ! -d "$token_dir" ]] && command -v mkdir >/dev/null 2>&1; then
    mkdir -p "$token_dir" 2>/dev/null && {
      record_check "token_log" "pass" "degraded" \
        "Token log directory created at $token_dir"
    } || {
      record_check "token_log" "degraded" "degraded" \
        "Cannot create token log directory at $token_dir — token tracking may fail"
    }
  else
    record_check "token_log" "degraded" "degraded" \
      "Token log path $token_path is not writable — set KANBAN_TOKEN_LOG"
  fi

  # Verify token_tracker.py is importable from repo root OR bundle scripts dir
  local token_ok=false
  if python3 -c "import sys; sys.path.insert(0, '.'); from scripts.token_tracker import log_token_run, log_from_env, log_from_agent_output" 2>/dev/null; then
    token_ok=true
  elif python3 -c "
import sys
sys.path.insert(0, sys.argv[1])
from token_tracker import log_token_run, log_from_env, log_from_agent_output
" "$SCRIPT_DIR" 2>/dev/null; then
    token_ok=true
  fi
  if [[ "$token_ok" == true ]]; then
    record_check "token_tracker_import" "pass" "degraded" \
      "scripts/token_tracker.py is importable — token reporting will work"
  else
    record_check "token_tracker_import" "degraded" "degraded" \
      "scripts/token_tracker.py not importable — token reporting will be silently skipped"
  fi
}

check_plan_backup() {
  # Copy the plan file to .hermes/kanban/plans/ for safe keeping
  # before decomposition can accidentally lose it.
  local plan_id="${KANBAN_PLAN_ID:-}"
  local plan_src=""
  
  if [[ -n "$plan_id" ]]; then
    # shellcheck source=lib/plan_paths.sh
    source "$SCRIPT_DIR/lib/plan_paths.sh"
    if command -v resolve_plan_file >/dev/null 2>&1; then
      plan_src="$(resolve_plan_file "$(pwd)" "$plan_id" "" 2>/dev/null || true)"
    fi
    if [[ -z "$plan_src" ]]; then
      for dir in ".hermes/kanban/plans" ".agent/plans"; do
        if [[ -f "$dir/${plan_id}.plan.md" ]]; then
          plan_src="$dir/${plan_id}.plan.md"
          break
        fi
        if [[ -f "$dir/${plan_id}.md" ]]; then
          plan_src="$dir/${plan_id}.md"
          break
        fi
      done
    fi
  fi
  
  if [[ -n "$plan_src" ]]; then
    local backup_dir=".hermes/kanban/plans"
    mkdir -p "$backup_dir"
    if cp "$plan_src" "$backup_dir/" 2>/dev/null; then
      record_check "plan_backup" "pass" "degraded" \
        "Plan file backed up: $plan_src → $backup_dir/"
    else
      record_check "plan_backup" "degraded" "degraded" \
        "Plan backup failed (disk full or permissions) — plan still in $plan_src"
    fi
  else
    record_check "plan_backup" "degraded" "degraded" \
      "No plan file found to backup (KANBAN_PLAN_ID=$plan_id). Plan may be conversationally built."
  fi
}

check_hermes_version() {
  if ! command -v hermes >/dev/null 2>&1; then
    record_check "hermes_version" "fail" "blocking" \
      "hermes CLI not on PATH — install Hermes Agent >= 0.16.0"
    return
  fi
  local ver_line
  ver_line="$(hermes --version 2>/dev/null | head -1 || true)"
  local ver_num=""
  ver_num="$(printf '%s' "$ver_line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
  if [[ -z "$ver_num" ]]; then
    record_check "hermes_version" "degraded" "degraded" \
      "Could not parse hermes --version ($ver_line); confirm >= 0.16.0 manually"
  else
    if python3 -c 'import sys
parts = [int(x) for x in sys.argv[1].split(".")]
need = (0, 16, 0)
sys.exit(0 if len(parts) >= 3 and tuple(parts[:3]) >= need else 1)' "$ver_num"; then
      record_check "hermes_version" "pass" "blocking" \
        "Hermes $ver_num >= 0.16.0 ($ver_line)"
    else
      record_check "hermes_version" "fail" "blocking" \
        "Hermes $ver_num < 0.16.0 required ($ver_line)"
    fi
  fi
  if hermes kanban --board "${KANBAN_BOARD:-default}" create --help 2>/dev/null | grep -q -- '--goal'; then
    record_check "kanban_goal_flag" "pass" "blocking" \
      "hermes kanban --board "${KANBAN_BOARD:-default}" create supports --goal"
  else
    record_check "kanban_goal_flag" "fail" "blocking" \
      "hermes kanban --board "${KANBAN_BOARD:-default}" create missing --goal; upgrade to Hermes >= 0.16.0"
  fi
}

check_kanban_auto_decompose() {
  if ! command -v hermes >/dev/null 2>&1; then
    return
  fi
  local cfg_path="${HERMES_HOME}/config.yaml"
  local val=""
  if [[ -f "$cfg_path" ]]; then
    # Try yaml parse first, grep fallback if unavailable
    val="$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f)
    print(str(cfg.get('kanban', {}).get('auto_decompose', 'NOT_FOUND')).lower())
except Exception:
    print('not_found')
" "$cfg_path" 2>/dev/null || true)"
    if [[ "$val" == "not_found" ]]; then
      val="$(grep -E '^[[:space:]]*auto_decompose:' "$cfg_path" 2>/dev/null | head -1 | sed 's/.*: *//; s/^\"//; s/\"$//' || true)"
    fi
  fi
  if [[ "$val" == "true" ]]; then
    record_check "kanban_auto_decompose" "fail" "blocking" \
      "kanban.auto_decompose is true — manual decomposition will duplicate cards; run: hermes config set kanban.auto_decompose false"
  elif [[ "$val" == "false" ]]; then
    record_check "kanban_auto_decompose" "pass" "degraded" \
      "kanban.auto_decompose is false (required for kanban-advanced manual decompose)"
  else
    record_check "kanban_auto_decompose" "degraded" "degraded" \
      "Could not read kanban.auto_decompose — confirm false before decomposition"
  fi
}

check_kanban_dispatch_stale_timeout() {
  if ! command -v hermes >/dev/null 2>&1; then
    return
  fi
  local cfg_path="${HERMES_HOME}/config.yaml"
  local val=""
  if [[ -f "$cfg_path" ]]; then
    val="$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f)
    print(cfg.get('kanban', {}).get('dispatch_stale_timeout_seconds', 'NOT_FOUND'))
except Exception:
    print('NOT_FOUND')
" "$cfg_path" 2>/dev/null || true)"
    if [[ "$val" == "NOT_FOUND" ]]; then
      val="$(grep -E '^[[:space:]]*dispatch_stale_timeout_seconds:' "$cfg_path" 2>/dev/null | head -1 | sed 's/.*: *//; s/^\"//; s/\"$//' || true)"
    fi
  fi
  if [[ "$val" == "0" ]]; then
    record_check "kanban_dispatch_stale_timeout" "degraded" "degraded" \
      "kanban.dispatch_stale_timeout_seconds is 0 (disabled) — re-run init or: hermes config set kanban.dispatch_stale_timeout_seconds 14400"
  elif [[ "$val" =~ ^[1-9][0-9]*$ ]]; then
    record_check "kanban_dispatch_stale_timeout" "pass" "degraded" \
      "kanban.dispatch_stale_timeout_seconds is set (stale reclaim enabled)"
  else
    record_check "kanban_dispatch_stale_timeout" "degraded" "degraded" \
      "Could not read kanban.dispatch_stale_timeout_seconds — re-run init or set 14400 (see dispatch-stale-timeout.md)"
  fi
}

check_memory_budget
check_hermes_version
check_kanban_auto_decompose
check_kanban_dispatch_stale_timeout
check_filesystem_coherence
check_kanban_db_integrity
check_secret_availability
check_api_reachability
check_gateway_health
check_profile_availability
check_model_reachability
check_coding_agent_cli_reachability
check_environment_parity
check_token_log
check_plan_backup

OVERALL_STATUS="pass"
if ((BLOCKING_FAILURES > 0)); then
  OVERALL_STATUS="fail"
elif ((DEGRADED_WARNINGS > 0)); then
  OVERALL_STATUS="degraded"
fi

CHECKS_JSON="$(IFS=,; printf '%s' "${CHECK_JSON_LINES[*]}")"

REPO_JSON="$(printf '%s' "$REPO_ROOT" | json_escape)"
ENV_JSON="$(printf '%s' "$ENVIRONMENT" | json_escape)"

printf '{'
printf '"status":"%s",' "$OVERALL_STATUS"
printf '"timestamp":"%s",' "$TIMESTAMP"
printf '"environment":%s,' "$ENV_JSON"
printf '"repo_root":%s,' "$REPO_JSON"
printf '"blocking_failures":%s,' "$BLOCKING_FAILURES"
printf '"degraded_warnings":%s,' "$DEGRADED_WARNINGS"
printf '"checks":[%s]' "$CHECKS_JSON"
printf '}\n'

if ((BLOCKING_FAILURES > 0)); then
  exit 1
fi
exit 0
