#!/usr/bin/env bash
# kanban_bundle.sh — resolve plugin checkout path for scripts and references.
# Source: source "$(dirname "$0")/lib/kanban_bundle.sh"  (from scripts/)

# shellcheck source=kanban_config.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/kanban_config.sh"

_resolve_kanban_bundle_root() {
    local repo_root="${1:-${HERMES_KANBAN_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
    local config_file bundle_path candidate

    config_file="$(_resolve_kanban_config_file "$repo_root" 2>/dev/null || true)"
    if [ -n "$config_file" ] && [ -f "$config_file" ]; then
        bundle_path="$(_read_config_key bundle_path "$config_file")"
        if [ -n "$bundle_path" ] && [ -f "$bundle_path/scripts/coding_agent_invoke.sh" ]; then
            printf '%s\n' "$bundle_path"
            return 0
        fi
    fi

    for candidate in \
        "${KANBAN_WORKFLOW_DIR:-}" \
        "${HERMES_HOME:-}/plugins/kanban-advanced" \
        "$repo_root/hermes-kanban-advanced-workflow" \
        "$repo_root/plugins/kanban-advanced"; do
        [ -n "$candidate" ] || continue
        if [ -f "$candidate/scripts/coding_agent_invoke.sh" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}
