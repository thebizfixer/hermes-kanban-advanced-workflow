#!/usr/bin/env bash
# resolve_notify_deliver.sh — print platform-neutral --deliver for lifecycle/completion crons.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=kanban_bundle.sh
source "$SCRIPT_DIR/kanban_bundle.sh"

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

BUNDLE_ROOT="$(_resolve_kanban_bundle_root "$REPO_ROOT" 2>/dev/null || true)"
PY_PATH="$SCRIPT_DIR"
if [ -n "$BUNDLE_ROOT" ] && [ -d "$BUNDLE_ROOT/plugin" ]; then
  PY_PATH="${BUNDLE_ROOT}:${PY_PATH}"
fi

PYTHONPATH="${PY_PATH}${PYTHONPATH:+:$PYTHONPATH}" python3 - "$REPO_ROOT" "$HERMES_HOME" <<'PY'
import sys
from pathlib import Path


def _load():
    try:
        from plugin.hermes_notify_deliver import resolve_notify_deliver
        return resolve_notify_deliver
    except ImportError:
        from hermes_notify_deliver import resolve_notify_deliver
        return resolve_notify_deliver


resolve = _load()
print(resolve(Path(sys.argv[1]), hermes_home=sys.argv[2]))
PY
