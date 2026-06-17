#!/usr/bin/env bash
# kanban_layout_acceptance.sh — presentation layout/a11y acceptance checks.
#
# Usage:
#   bash kanban_layout_acceptance.sh --workspace <repo_root> [--card-body-file <path>] [--rules-json '<json>']
#   bash kanban_layout_acceptance.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE=""
BODY_FILE=""
RULES_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --card-body-file) BODY_FILE="$2"; shift 2 ;;
    --rules-json) RULES_JSON="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: kanban_layout_acceptance.sh --workspace <path> [--card-body-file <file>] [--rules-json <json>]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$WORKSPACE" ]]; then
  echo "ERROR: --workspace required" >&2
  exit 2
fi

BODY=""
if [[ -n "$BODY_FILE" && -f "$BODY_FILE" ]]; then
  BODY="$(cat "$BODY_FILE")"
fi

export WORKSPACE BODY RULES_JSON
python3 - "$SCRIPT_DIR" <<'PY'
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from presentation_acceptance import run_presentation_checks

workspace = os.environ["WORKSPACE"]
body = os.environ.get("BODY", "")
rules = os.environ.get("RULES_JSON", "")
if not body.strip():
    print("SKIP: no card body provided")
    sys.exit(0)
ok, err = run_presentation_checks(body, workspace, rules)
if ok:
    print("ALLOW: presentation acceptance")
    sys.exit(0)
print(f"DENY: {err or 'E028'}")
sys.exit(1)
PY
