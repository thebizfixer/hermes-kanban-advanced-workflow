#!/usr/bin/env bash
# coding_agent_env.sh — ensure HOME for coding-agent CLIs (OAuth / credential paths).
#
# Gateway workers under systemd with SetLoginEnvironment=no often inherit no HOME.
# Cursor agent (set -u) crashes: CONFIG_DIR="${HOME}/.config/cursor"
#
# Source from coding_agent_invoke.sh and worker smoke blocks:
#   source "$(dirname "$0")/lib/coding_agent_env.sh"
#   ensure_coding_agent_home

ensure_coding_agent_home() {
  if [ -n "${HOME:-}" ]; then
    return 0
  fi
  if command -v getent >/dev/null 2>&1; then
    HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6)"
  fi
  if [ -z "${HOME:-}" ] && command -v python3 >/dev/null 2>&1; then
    HOME="$(python3 -c 'from pathlib import Path; print(Path.home())' 2>/dev/null || true)"
  fi
  if [ -z "${HOME:-}" ]; then
    echo "[coding_agent_env] ERROR: HOME is unset — set HOME in project .env or gateway unit" >&2
    return 1
  fi
  export HOME
}
