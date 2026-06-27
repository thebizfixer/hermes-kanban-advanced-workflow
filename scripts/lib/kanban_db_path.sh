#!/usr/bin/env bash
# kanban_db_path.sh — resolve the correct kanban DB path per Hermes board
# Source this file, then use $KANBAN_DB_PATH or call resolve_kanban_db().
#
#   HERMES_KANBAN_BOARD=my-board → $HERMES_HOME/kanban/boards/my-board/kanban.db
#   HERMES_KANBAN_BOARD=default   → $HERMES_HOME/kanban.db   (default board)
#   HERMES_KANBAN_BOARD unset     → $HERMES_HOME/kanban.db   (backward compat)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=hermes_home.sh
source "$SCRIPT_DIR/hermes_home.sh" 2>/dev/null || {
    HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
}

resolve_kanban_db() {
    local board="${HERMES_KANBAN_BOARD:-}"
    if [[ -n "$board" && "$board" != "default" ]]; then
        echo "${HERMES_HOME}/kanban/boards/${board}/kanban.db"
    else
        echo "${HERMES_HOME}/kanban.db"
    fi
}

KANBAN_DB_PATH="$(resolve_kanban_db)"
export KANBAN_DB_PATH
