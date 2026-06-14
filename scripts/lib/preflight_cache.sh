#!/usr/bin/env bash
# preflight_cache.sh — read/write .hermes/kanban/preflight_cache.json
set -euo pipefail

preflight_cache_file() {
  local base="${1:-}"
  if [[ -z "$base" ]]; then
    base="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  fi
  printf '%s\n' "${base}/.hermes/kanban/preflight_cache.json"
}

preflight_cache_fresh() {
  local binary="${1:-agent}"
  local repo_root="${2:-}"
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local repo="${repo_root:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  PYTHONPATH="${repo}:${PYTHONPATH:-}" python3 - "$repo" "$binary" <<'PY'
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
BINARY = sys.argv[2]
sys.path.insert(0, str(ROOT))
from plugin.coding_agent_auth_cache import is_preflight_cache_fresh

raise SystemExit(0 if is_preflight_cache_fresh(BINARY, ROOT) else 1)
PY
}
