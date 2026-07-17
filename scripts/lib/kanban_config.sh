#!/usr/bin/env bash
# kanban_config.sh — Shared config resolution for kanban-advanced scripts.
# Source from other scripts: source "$SCRIPT_DIR/lib/kanban_config.sh"

# resolve_project_root [start_dir]
# Mirrors plugin.config_overlay.resolve_project_root — prefers kanban overlay over .git
# (plugin install dirs often have their own .git).
resolve_project_root() {
    local start_dir="${1:-${SCRIPT_DIR:-$PWD}}"
    if [ -n "${KANBAN_PROJECT_ROOT:-}" ]; then
        (cd "$KANBAN_PROJECT_ROOT" && pwd)
        return 0
    fi
    if [ -n "${HERMES_PROJECT_ROOT:-}" ]; then
        (cd "$HERMES_PROJECT_ROOT" && pwd)
        return 0
    fi
    if [ -n "${HERMES_KANBAN_CONFIG:-}" ] && [ -f "$HERMES_KANBAN_CONFIG" ]; then
        (cd "$(dirname "$HERMES_KANBAN_CONFIG")/../.." && pwd)
        return 0
    fi

    # Try git root before CWD walk — cron context may have different CWD than repo root.
    # git rev-parse always outputs forward slashes on all platforms.
    local git_root
    if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
        printf '%s\n' "$git_root"
        return 0
    fi

    # Fall back to $HERMES_HOME parent directory (project containing .hermes/)
    if [ -n "${HERMES_HOME:-}" ]; then
        local hermes_parent
        hermes_parent="$(cd "$HERMES_HOME/.." 2>/dev/null && pwd)" || true
        if [ -n "$hermes_parent" ] && [ -f "$hermes_parent/.hermes/kanban-overrides/kanban-config.yaml" ]; then
            printf '%s\n' "$hermes_parent"
            return 0
        fi
    fi

    # Last resort: walk up from start_dir (original CWD-based behavior)
    local dir
    dir="$(cd "$start_dir" && pwd)"
    local config_hit="" git_hit="" env_hit=""
    while [[ "$dir" != "/" ]]; do
        if [[ -z "$config_hit" && -f "$dir/.hermes/kanban-overrides/kanban-config.yaml" ]]; then
            config_hit="$dir"
        fi
        if [[ -z "$git_hit" && -d "$dir/.git" ]]; then
            git_hit="$dir"
        fi
        if [[ -z "$env_hit" && -f "$dir/.env" ]]; then
            env_hit="$dir"
        fi
        dir="$(dirname "$dir")"
    done
    if [[ -n "$config_hit" ]]; then
        printf '%s\n' "$config_hit"
        return 0
    fi
    if [[ -n "$git_hit" ]]; then
        printf '%s\n' "$git_hit"
        return 0
    fi
    if [[ -n "$env_hit" ]]; then
        printf '%s\n' "$env_hit"
        return 0
    fi
    (cd "$start_dir" && pwd)
}

_read_config_key() {
    local key="$1" config_file="$2"
    grep -E "^${key}:" "$config_file" 2>/dev/null \
        | head -1 | sed "s/^${key}: *//; s/^['\"]//; s/['\"]$//"
}

_resolve_kanban_config_file() {
    local repo_root="${1:-}"
    if [ -n "${HERMES_KANBAN_CONFIG:-}" ] && [ -f "$HERMES_KANBAN_CONFIG" ]; then
        printf '%s\n' "$HERMES_KANBAN_CONFIG"
        return 0
    fi
    if [ -n "$repo_root" ] && [ -f "$repo_root/.hermes/kanban-overrides/kanban-config.yaml" ]; then
        printf '%s\n' "$repo_root/.hermes/kanban-overrides/kanban-config.yaml"
        return 0
    fi
    return 1
}

_load_branch_config() {
    local repo_root="${1:-}"
    CONFIG_FILE=""
    WORKING_BRANCH=""
    TRIGGER_BRANCH=""

    CONFIG_FILE="$(_resolve_kanban_config_file "$repo_root" || true)"
    if [ -z "$CONFIG_FILE" ] || [ ! -f "$CONFIG_FILE" ]; then
        echo "[kanban-governance] ERROR: config not found" >&2
        echo "[kanban-governance] Run: hermes kanban-advanced init" >&2
        echo "[kanban-governance] If running as cron: check 'hermes cron list' for workdir vs actual CWD" >&2
        return 1
    fi

    WORKING_BRANCH="$(_read_config_key working_branch "$CONFIG_FILE")"
    TRIGGER_BRANCH="$(_read_config_key trigger_branch "$CONFIG_FILE")"

    if [ -z "$WORKING_BRANCH" ]; then
        echo "[kanban-governance] ERROR: working_branch must be set in $CONFIG_FILE" >&2
        return 1
    fi
    return 0
}

_read_escalation_max() {
    local level="$1" config_file="$2"
    python3 - "$level" "$config_file" <<'PY'
import sys
from pathlib import Path

level = sys.argv[1]
path = Path(sys.argv[2])
text = path.read_text(encoding="utf-8")
in_block = False
for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("escalation_max_attempts:"):
        in_block = True
        continue
    if in_block:
        if not line.startswith((" ", "\t")):
            break
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip().split("#", 1)[0].strip()
        if key == level:
            print(val)
            sys.exit(0)
print("", end="")
PY
}

_load_escalation_config() {
    local config_file="${1:-}"
    ESCALATION_MAX_CODING_AGENT=""
    ESCALATION_MAX_WORKER=""
    ESCALATION_MAX_ORCHESTRATOR=""

    if [ -z "$config_file" ] || [ ! -f "$config_file" ]; then
        echo "[kanban-governance] ERROR: escalation_max_attempts config not found — run hermes kanban-advanced init" >&2
        return 1
    fi

    ESCALATION_MAX_CODING_AGENT="$(_read_escalation_max coding_agent "$config_file")"
    ESCALATION_MAX_WORKER="$(_read_escalation_max worker "$config_file")"
    ESCALATION_MAX_ORCHESTRATOR="$(_read_escalation_max orchestrator "$config_file")"

    if [ -z "$ESCALATION_MAX_CODING_AGENT" ] || [ -z "$ESCALATION_MAX_WORKER" ] || [ -z "$ESCALATION_MAX_ORCHESTRATOR" ]; then
        echo "[kanban-governance] ERROR: escalation_max_attempts not set in $config_file — run hermes kanban-advanced init" >&2
        return 1
    fi
    return 0
}

# walk_away_mode: full unattended run including auto post-exec + completion notify.
# Legacy: notify_on_complete key, NOTIFY_ON_COMPLETE / WALK_AWAY_MODE env.
_walk_away_mode_enabled() {
    local config_file="${1:-}"
    local val="${WALK_AWAY_MODE:-}"
    if [[ -z "$val" && -n "${NOTIFY_ON_COMPLETE:-}" ]]; then
        val="${NOTIFY_ON_COMPLETE}"
    fi
    if [[ -z "$val" && -n "$config_file" && -f "$config_file" ]]; then
        val="$(_read_config_key walk_away_mode "$config_file")"
        if [[ -z "$val" ]]; then
            val="$(_read_config_key notify_on_complete "$config_file")"
        fi
    fi
    if [[ -z "$val" ]]; then
        val="false"
    fi
    [[ "$val" == "true" || "$val" == "1" ]]
}

_resolve_active_plan_id() {
    local repo_root="${1:-}"
    local plan_id="${HERMES_KANBAN_PLAN_ID:-}"
    # Single Python invocation: prefer active:true plans sorted by file mtime
    # (newest first, breaks the alphabetical tiebreaker when multiple plans are active).
    if [[ -z "$plan_id" && -n "$repo_root" ]]; then
        plan_id="$(python3 -c "
import json, glob, os, sys

mem_dir = os.path.join(r'$repo_root', '.hermes', 'kanban', 'memory')
files = glob.glob(os.path.join(mem_dir, '*.json'))
candidates = []
for f in files:
    try:
        d = json.load(open(f))
        pid = d.get('plan_id', '')
        if not pid:
            continue
        active = d.get('active', False)
        mtime = os.path.getmtime(f)
        candidates.append((active, mtime, pid))
    except Exception:
        pass

if candidates:
    # Sort: active:True first, then by mtime descending (newest wins tiebreaker)
    candidates.sort(key=lambda x: (not x[0], -x[1]))
    print(candidates[0][2])
" 2>/dev/null || true)"
    fi
    # Fallback to legacy singleton file
    if [[ -z "$plan_id" && -n "$repo_root" && -f "$repo_root/.hermes/kanban/logs/lifecycle_plan_id" ]]; then
        plan_id="$(<"$repo_root/.hermes/kanban/logs/lifecycle_plan_id")"
    fi
    printf '%s\n' "$plan_id"
}
