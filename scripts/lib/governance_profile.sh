#!/usr/bin/env bash
# governance_profile.sh — Resolve advisory | balanced | strict for governance scripts.
# Source after kanban_config.sh when repo root is known.

GOVERNANCE_PROFILE="${KANBAN_POLICY_PROFILE:-balanced}"

_normalize_governance_profile() {
  local v="${1:-}"
  v="$(echo "$v" | tr '[:upper:]' '[:lower:]')"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  case "$v" in
    advisory|balanced|strict) printf '%s\n' "$v" ;;
    *) printf '%s\n' "balanced" ;;
  esac
}

load_governance_profile() {
  local repo_root="${1:-}"
  local override="${2:-}"

  if [ -n "$override" ]; then
    GOVERNANCE_PROFILE="$(_normalize_governance_profile "$override")"
    export KANBAN_POLICY_PROFILE="$GOVERNANCE_PROFILE"
    return 0
  fi

  local config_file=""
  config_file="$(_resolve_kanban_config_file "$repo_root" 2>/dev/null || true)"
  if [ -n "$config_file" ] && [ -f "$config_file" ]; then
    local from_config
    from_config="$(_read_config_key policy_profile "$config_file")"
    if [ -n "$from_config" ]; then
      GOVERNANCE_PROFILE="$(_normalize_governance_profile "$from_config")"
      export KANBAN_POLICY_PROFILE="$GOVERNANCE_PROFILE"
      return 0
    fi
  fi

  if [ -n "${KANBAN_POLICY_PROFILE:-}" ]; then
    GOVERNANCE_PROFILE="$(_normalize_governance_profile "$KANBAN_POLICY_PROFILE")"
    export KANBAN_POLICY_PROFILE="$GOVERNANCE_PROFILE"
    return 0
  fi

  GOVERNANCE_PROFILE="balanced"
  export KANBAN_POLICY_PROFILE="$GOVERNANCE_PROFILE"
}

governance_warnings_block() {
  [ "$GOVERNANCE_PROFILE" = "strict" ]
}

governance_failures_block() {
  [ "$GOVERNANCE_PROFILE" != "advisory" ]
}
