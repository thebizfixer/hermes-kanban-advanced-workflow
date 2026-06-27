#!/usr/bin/env bash
# plan_paths.sh — bash wrapper for scripts/lib/plan_paths.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Platform-native path separator — colon on Linux, semicolon on Windows.
_PY_SEP="$("python3" -c "import os; print(os.pathsep)" 2>/dev/null || echo ':')"
# On Windows (Git Bash), pwd returns /c/Users/... format which native
# Windows Python can't resolve. Convert paths to native format.
if [ "$_PY_SEP" = ";" ] && command -v cygpath >/dev/null 2>&1; then
  SCRIPT_DIR="$(cygpath -w "$SCRIPT_DIR")"
  BUNDLE_ROOT="$(cygpath -w "$BUNDLE_ROOT")"
fi

resolve_plan_file() {
  local repo_root="${1:?repo_root}"
  local plan_id="${2:?plan_id}"
  local hint="${3:-}"
  PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+${_PY_SEP}${PYTHONPATH}}" python3 -c "
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

ensure_canonical_plan() {
  local repo_root="${1:?repo_root}"
  local plan_id="${2:?plan_id}"
  local hint="${3:-}"
  PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+${_PY_SEP}${PYTHONPATH}}" python3 -c "
import sys
from plan_paths import ensure_canonical_plan
from pathlib import Path
repo, plan_id, hint = sys.argv[1], sys.argv[2], sys.argv[3]
path = ensure_canonical_plan(repo, plan_id, hint or None)
if path:
    try:
        print(path.relative_to(Path(repo).resolve()).as_posix())
    except ValueError:
        print(path)
" "$repo_root" "$plan_id" "$hint"
}
