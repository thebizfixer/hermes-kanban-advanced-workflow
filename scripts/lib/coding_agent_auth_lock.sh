#!/usr/bin/env bash
# coding_agent_auth_lock.sh — Serialize Cursor agent OAuth refresh (flock / fcntl).
#
# Usage (after sourcing coding_agent_env.sh):
#   run_with_coding_agent_auth_lock <command...>
#
# Lock file: $HERMES_HOME/.locks/coding-agent-auth.lock
set -euo pipefail

CODING_AGENT_AUTH_LOCK_WAIT_SECONDS="${CODING_AGENT_AUTH_LOCK_WAIT_SECONDS:-120}"
CODING_AGENT_AUTH_LOCK_STALE_SECONDS="${CODING_AGENT_AUTH_LOCK_STALE_SECONDS:-600}"

ensure_coding_agent_auth_lock_dir() {
  local base="${HERMES_HOME:-${HOME:-}/.hermes}"
  mkdir -p "${base}/.locks"
  printf '%s\n' "${base}/.locks/coding-agent-auth.lock"
}

clear_stale_coding_agent_auth_lock() {
  local lockfile="$1"
  local stale="${CODING_AGENT_AUTH_LOCK_STALE_SECONDS}"
  if [[ ! -f "$lockfile" ]]; then
    return 0
  fi
  local mtime now age
  mtime="$(stat -c %Y "$lockfile" 2>/dev/null || stat -f %m "$lockfile" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  age=$((now - mtime))
  if (( age > stale )); then
    rm -f "$lockfile"
  fi
}

run_with_coding_agent_auth_lock() {
  if [[ $# -lt 1 ]]; then
    echo "[coding_agent_auth_lock] run_with_coding_agent_auth_lock: missing command" >&2
    return 2
  fi
  if ! command -v flock >/dev/null 2>&1; then
    echo "[coding_agent_auth_lock] flock not found — required on gateway host (use WSL/Linux)" >&2
    return 127
  fi
  local lockfile wait
  lockfile="$(ensure_coding_agent_auth_lock_dir)"
  clear_stale_coding_agent_auth_lock "$lockfile"
  wait="$CODING_AGENT_AUTH_LOCK_WAIT_SECONDS"
  if ! flock -n "$lockfile" true 2>/dev/null; then
    echo "[coding_agent_auth_lock] waiting for lock (up to ${wait}s)…" >&2
  fi
  if ! flock -w "$wait" "$lockfile" "$@"; then
    echo "[coding_agent_auth_lock] lock busy after ${wait}s — stale holder? rm -f ${lockfile}" >&2
    return 1
  fi
}

# Option A pre-warm: refresh Cursor OAuth once before parallel worker dispatch.
prewarm_coding_agent_auth() {
  local binary="${KANBAN_CODING_AGENT:-agent}"
  case "$binary" in
    agent) ;;
    *) return 0 ;;
  esac
  if ! command -v "$binary" >/dev/null 2>&1; then
    return 0
  fi
  echo "[coding_agent_auth_lock] pre-warming Cursor OAuth token…" >&2
  run_with_coding_agent_auth_lock "$binary" -p "echo ok" --trust --output-format json >/dev/null 2>&1 \
    || return $?
}
