#!/usr/bin/env bash
# kanban_config.sh — Shared config resolution for kanban-advanced scripts.
# Source from other scripts: source "$SCRIPT_DIR/lib/kanban_config.sh"

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
        return 1
    fi

    WORKING_BRANCH="$(_read_config_key working_branch "$CONFIG_FILE")"
    TRIGGER_BRANCH="$(_read_config_key trigger_branch "$CONFIG_FILE")"

    if [ -z "$WORKING_BRANCH" ] || [ -z "$TRIGGER_BRANCH" ]; then
        echo "[kanban-governance] ERROR: working_branch and trigger_branch must both be set in $CONFIG_FILE" >&2
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
