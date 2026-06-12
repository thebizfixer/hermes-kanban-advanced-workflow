#!/usr/bin/env bash
# plan_paths.sh — bash wrapper for scripts/lib/plan_paths.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

resolve_plan_file() {
  local repo_root="${1:?repo_root}"
  local plan_id="${2:?plan_id}"
  local hint="${3:-}"
  PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}" python3 -c "
import sys
from plan_paths import resolve_plan_file
from pathlib import Path
repo, plan_id, hint = sys.argv[1], sys.argv[2], sys.argv[3]
path = resolve_plan_file(repo, plan_id, hint or None)
if path:
    try:
        print(path.relative_to(Path(repo).resolve()).as_posix())
    except ValueError:
        print(path)
" "$repo_root" "$plan_id" "$hint"
}
