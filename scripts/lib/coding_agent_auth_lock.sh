#!/usr/bin/env bash
# coding_agent_auth_lock.sh — Serialize Cursor agent OAuth refresh (flock).
#
# Usage (after sourcing coding_agent_env.sh):
#   run_with_coding_agent_auth_lock <command...>
#
# Lock file: $HERMES_HOME/.locks/coding-agent-auth.lock (120s wait).
set -euo pipefail

CODING_AGENT_AUTH_LOCK_WAIT_SECONDS="${CODING_AGENT_AUTH_LOCK_WAIT_SECONDS:-120}"

ensure_coding_agent_auth_lock_dir() {
  local base="${HERMES_HOME:-${HOME:-}/.hermes}"
  mkdir -p "${base}/.locks"
  printf '%s\n' "${base}/.locks/coding-agent-auth.lock"
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
  local lockfile
  lockfile="$(ensure_coding_agent_auth_lock_dir)"
  if ! flock -n "$lockfile" true 2>/dev/null; then
    echo "[coding_agent_auth_lock] waiting for lock (up to ${CODING_AGENT_AUTH_LOCK_WAIT_SECONDS}s)…" >&2
  fi
  flock -w "$CODING_AGENT_AUTH_LOCK_WAIT_SECONDS" "$lockfile" "$@"
}
