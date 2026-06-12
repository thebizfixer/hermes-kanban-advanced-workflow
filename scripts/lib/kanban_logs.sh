#!/usr/bin/env bash
# Resolve kanban log directory: project .hermes/kanban/logs first, else $HERMES_HOME/kanban/logs.
#
# Usage (after sourcing):
#   LOGDIR="$(kanban_logs_dir "${REPO_ROOT:-$(pwd)}")"

kanban_logs_dir() {
  local start="${1:-$(pwd)}"
  local d="$start"
  local i=0
  while [[ -n "$d" && $i -lt 12 ]]; do
    if [[ -d "$d/.hermes/kanban" ]]; then
      printf '%s\n' "$d/.hermes/kanban/logs"
      return 0
    fi
    local parent
    parent="$(dirname "$d")"
    [[ "$parent" == "$d" ]] && break
    d="$parent"
    i=$((i + 1))
  done
  printf '%s\n' "${HERMES_HOME:-$HOME/.hermes}/kanban/logs"
}
