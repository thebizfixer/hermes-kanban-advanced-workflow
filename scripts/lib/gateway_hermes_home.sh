# shellcheck shell=bash
# gateway_hermes_home.sh — resolve the gateway-visible Hermes state directory.
#
# Cron jobs created from a profile-scoped session land in
# $HERMES_HOME/profiles/<name>/cron/jobs.json, but the gateway scheduler reads
# the main store ($HOME/.hermes/cron/jobs.json). Use KANBAN_GATEWAY_HERMES_HOME
# for cron create/list/remove operations only — do not change kanban.db paths.
#
# Usage:
#   source "$(dirname "$0")/lib/gateway_hermes_home.sh"
#   HERMES_HOME="$KANBAN_GATEWAY_HERMES_HOME" hermes cron create ...

_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=hermes_home.sh
source "$_LIB_DIR/hermes_home.sh"
_PLUGIN_ROOT="$(cd "$_LIB_DIR/../.." && pwd)"
# Platform-native path separator — colon on Linux, semicolon on Windows.
_PY_SEP="$("python3" -c "import os; print(os.pathsep)" 2>/dev/null || echo ':')"

_resolve_gateway_hermes_home() {
  PYTHONPATH="${_PLUGIN_ROOT}${PYTHONPATH:+${_PY_SEP}${PYTHONPATH}}" python3 - "$HERMES_HOME" <<'PY'
import sys
from plugin.hermes_gateway_home import resolve_gateway_hermes_home
print(resolve_gateway_hermes_home(sys.argv[1]))
PY
}

if [[ -z "${KANBAN_GATEWAY_HERMES_HOME:-}" ]]; then
  export KANBAN_GATEWAY_HERMES_HOME="$(_resolve_gateway_hermes_home)"
fi

kanban_is_profile_scoped_hermes_home() {
  PYTHONPATH="${_PLUGIN_ROOT}${PYTHONPATH:+${_PY_SEP}${PYTHONPATH}}" python3 - "$HERMES_HOME" <<'PY'
import sys
from plugin.hermes_gateway_home import is_profile_scoped_hermes_home
raise SystemExit(0 if is_profile_scoped_hermes_home(sys.argv[1]) else 1)
PY
}
