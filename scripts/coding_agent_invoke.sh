#!/usr/bin/env bash
# coding_agent_invoke.sh — headless smoke or dispatch for KANBAN_CODING_AGENT
#
# Usage:
#   coding_agent_invoke.sh smoke
#   coding_agent_invoke.sh dispatch "<full prompt>"
#
# Env resolution (first wins):
#   1. Already exported in environment (gateway sets these)
#   2. Project .env (written by dashboard init/save — sourced here)
#   3. Hardcoded fallback: hermes
#
#   KANBAN_CODING_AGENT_MODEL  (default: auto)
#   HERMES_KANBAN_PLAN_ID      Plan ID for token attribution
#   HERMES_KANBAN_TASK         Task ID for token attribution
set -euo pipefail
export LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/coding_agent_env.sh
source "$SCRIPT_DIR/lib/coding_agent_env.sh"
# shellcheck source=lib/coding_agent_auth_lock.sh
source "$SCRIPT_DIR/lib/coding_agent_auth_lock.sh"
# shellcheck source=lib/preflight_cache.sh
source "$SCRIPT_DIR/lib/preflight_cache.sh"
ensure_coding_agent_home

MODE="${1:-smoke}"
PROMPT="${2:-say ok}"
REPO_ROOT="${HERMES_KANBAN_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# Source project .env for coding-agent vars set by dashboard init/save.
# The gateway doesn't source .env for spawned child processes, so we
# load it here so non-default agent configs reach workers.
# Only sets vars that aren't already in the environment (gateway wins).
if [ -f "$REPO_ROOT/.env" ]; then
  for _var in KANBAN_CODING_AGENT KANBAN_CODING_AGENT_MODEL KANBAN_CODING_AGENT_PROVIDER KANBAN_CODING_AGENT_PROFILE; do
    if [ -z "${!_var:-}" ]; then
      _val="$(grep "^${_var}=" "$REPO_ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2-)"
      [ -n "${_val:-}" ] && export "${_var}=${_val}"
    fi
  done
fi

BINARY="${KANBAN_CODING_AGENT:-hermes}"
MODEL="${KANBAN_CODING_AGENT_MODEL:-auto}"
PROVIDER="${KANBAN_CODING_AGENT_PROVIDER:-}"
PROFILE="${KANBAN_CODING_AGENT_PROFILE:-}"

model_is_auto() {
  case "${MODEL,,}" in
    ""|auto|default) return 0 ;;
    *) return 1 ;;
  esac
}

append_grok_headless_args() {
  local -n _out=$1
  local prompt="$2"
  if "$BINARY" --help 2>&1 | grep -qE -- '--single|-p, --single'; then
    _out=( -p "$prompt" --output-format json --always-approve )
  else
    _out=( --prompt "$prompt" --format json )
  fi
}

append_model_args() {
  local -n _out=$1
  if model_is_auto; then
    return 0
  fi
  # All known binaries support --model
  _out+=(--model "$MODEL")
}

append_provider_args() {
  local -n _out=$1
  if [[ -z "${PROVIDER:-}" ]]; then
    return 0
  fi
  _out+=(--provider "$PROVIDER")
}

# ── Unified dispatch: capture, log tokens, output to stdout ────────────

_dispatch_and_log() {
  # Run the coding agent, capture stdout+stderr to a temp file,
  # extract tokens via log_invoke_tokens.py (handles JSON + text estimation),
  # then cat the output to stdout for the worker to capture.
  local -a agent_args=("$@")
  local out_file
  out_file="$(mktemp)"

  if [[ -z "${HERMES_KANBAN_TASK:-}" ]]; then
    echo "[coding_agent_invoke] WARNING: HERMES_KANBAN_TASK not set — token log task_id will be empty" >&2
  fi

  local rc=0
  if run_with_coding_agent_auth_lock "$BINARY" "${agent_args[@]}" >"$out_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  # Always attempt token logging — log_invoke_tokens.py handles:
  #   - JSON with usage block → exact tokens (source=agent)
  #   - Text-only output → estimated tokens (source=estimated)
  #   - Empty/unparseable output → no-op (returns 0)
  HERMES_KANBAN_PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}" \
  HERMES_KANBAN_TASK="${HERMES_KANBAN_TASK:-}" \
    python3 "$SCRIPT_DIR/log_invoke_tokens.py" --output-file "$out_file" 2>/dev/null || true

  # Save agent output to expected path before cat so E020 eval check finds it.
  local agent_output_path
  agent_output_path="${KANBAN_TEMP:-${TMPDIR:-${TEMP:-/tmp}}}/agent_output_${HERMES_KANBAN_TASK:-unknown}.json"
  cp "$out_file" "$agent_output_path" 2>/dev/null || true

  # Output captured content to stdout (worker captures this)
  cat "$out_file"
  rm -f "$out_file"

  return "$rc"
}

# ── Hermes-specific dispatch: authoritative token metering ─────────────

_dispatch_hermes_and_meter() {
  # For the 'hermes' coding agent, tokens are metered via Hermes insights
  # delta rather than agent self-reporting. Hermes records token usage from
  # provider response headers (not from agent output), so this is
  # non-self-reporting and authoritative.
  # Flow: snapshot → dispatch → delta → log authoritative counts
  local -a agent_args=("$@")
  local out_file
  out_file="$(mktemp)"

  if [[ -z "${HERMES_KANBAN_TASK:-}" ]]; then
    echo "[coding_agent_invoke] WARNING: HERMES_KANBAN_TASK not set — token log task_id will be empty" >&2
  fi

  # Clean up stale baseline on interrupt (SIGTERM/SIGINT) so next run starts clean.
  # BASELINE_FILE path matches hermes_token_meter.py's tempfile.gettempdir() location.
  local baseline_file
  baseline_file="$(python3 -c "
import tempfile, os
from pathlib import Path
tmp = Path(tempfile.gettempdir()).as_posix()
if not os.path.isabs(tmp):
    win_tmp = os.environ.get('TEMP') or os.environ.get('TMP') or ''
    if win_tmp and os.path.isabs(win_tmp):
        tmp = Path(win_tmp).as_posix()
    else:
        tmp = (Path.home() / 'tmp').as_posix()
print(Path(tmp) / 'hermes_token_meter_baseline.json')
")"
  trap 'rm -f "$baseline_file" 2>/dev/null' EXIT INT TERM

  # Snapshot current Hermes token state (errors go to stderr for debugging).
  # Do NOT use || true — silent failures cause estimated fallback instead of
  # authoritative hermes_insights. Capture exit code explicitly and warn.
  local snapshot_ok=true
  python3 "$SCRIPT_DIR/hermes_token_meter.py" snapshot || snapshot_ok=false
  if ! $snapshot_ok; then
    echo "[WARNING] Token snapshot failed — will attempt delta with existing baseline (if any)" >&2
  fi

  local rc=0
  if run_with_coding_agent_auth_lock "$BINARY" "${agent_args[@]}" >"$out_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  # Log authoritative token delta from Hermes insights.
  # Errors are visible in worker output — critical for diagnosing metering issues.
  # Keep || meter_rc=$? so a metering failure doesn't block the card from completing.
  local meter_rc=0
  HERMES_KANBAN_PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}" \
  HERMES_KANBAN_TASK="${HERMES_KANBAN_TASK:-}" \
    python3 "$SCRIPT_DIR/hermes_token_meter.py" delta \
      --plan-id "${HERMES_KANBAN_PLAN_ID:-}" \
      --task-id "${HERMES_KANBAN_TASK:-}" \
      --source hermes_insights || meter_rc=$?

  # Only run log_invoke_tokens.py as fallback when BOTH snapshot and delta failed.
  # If snapshot failed but delta succeeded (baseline from prior run), the delta
  # result is authoritative — do not overwrite with estimated.
  if [ "$meter_rc" -ne 0 ] && ! $snapshot_ok; then
    echo "[WARNING] Both snapshot and delta failed — falling back to estimated metering" >&2
    HERMES_KANBAN_PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}" \
    HERMES_KANBAN_TASK="${HERMES_KANBAN_TASK:-}" \
      python3 "$SCRIPT_DIR/log_invoke_tokens.py" --output-file "$out_file" || true
  elif [ "$meter_rc" -ne 0 ]; then
    echo "[WARNING] Token delta failed but snapshot was OK — baseline/delta mismatch, check hermes insights" >&2
  fi

  # Save agent output to expected path before cat so E020 eval check finds it.
  # Path must match step_7_agent_output_capture in kanban_evaluation_chain.py.
  local agent_output_path
  agent_output_path="${KANBAN_TEMP:-${TMPDIR:-${TEMP:-/tmp}}}/agent_output_${HERMES_KANBAN_TASK:-unknown}.json"
  cp "$out_file" "$agent_output_path" 2>/dev/null || true

  # Output captured content to stdout (worker captures this)
  cat "$out_file"

  # Post-agent check: detect if coding agent prematurely completed the card
  if [[ -n "${HERMES_KANBAN_TASK:-}" ]]; then
    local agent_status
    agent_status=$(hermes kanban show "$HERMES_KANBAN_TASK" 2>/dev/null | grep '^  status:' | awk '{print $2}')
    if [[ "$agent_status" == "done" || "$agent_status" == "completed" ]]; then
      echo "[WARN] Agent completed card $HERMES_KANBAN_TASK prematurely (status=$agent_status). Eval chain will run post-completion for verification." >&2
    fi
  fi

  rm -f "$out_file"

  return "$rc"
}

# ── Smoke ──────────────────────────────────────────────────────────────

_run_agent() {
  local attempt=1
  local max_attempts=2
  while [[ "$attempt" -le "$max_attempts" ]]; do
  if run_with_coding_agent_auth_lock "$BINARY" "${args[@]}"; then
      return 0
    fi
    local rc=$?
    if [[ "$attempt" -eq "$max_attempts" ]]; then
      return "$rc"
    fi
    if [[ "$MODE" == "smoke" ]]; then
      echo "[coding_agent_invoke] auth smoke failed — retry once after peer refresh" >&2
      attempt=$((attempt + 1))
      continue
    fi
    return "$rc"
  done
}

_run_handshake() {
  echo "[coding_agent_invoke] preflight cache fresh — handshake only" >&2
  CODING_AGENT_AUTH_LOCK_WAIT_SECONDS="${CODING_AGENT_AUTH_LOCK_WAIT_SECONDS:-5}"
  case "$BINARY" in
    agent|cursor-agent)
      args=( -p "hello" --trust )
      append_model_args args
      _run_agent
      return $?
      ;;
    *)
      echo "[coding_agent_invoke] cache fresh — skipping full smoke for ${BINARY}" >&2
      return 0
      ;;
  esac
}

if [[ "$MODE" == "smoke" ]] && preflight_cache_fresh "$BINARY" "$REPO_ROOT"; then
  _run_handshake
  exit $?
fi

# ── Binary-specific dispatch ───────────────────────────────────────────

case "$BINARY" in
  agent|cursor-agent)
    # Cursor: -p = --print; --output-format requires -p; --trust required in worktrees
    args=( -p "$PROMPT" --output-format json --trust )
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    _run_agent
    exit $?
    ;;

  claude)
    args=( -p "$PROMPT" --output-format json --dangerously-skip-permissions )
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  codex)
    args=( exec --json -a never )
    if [ "$MODE" = "dispatch" ]; then
      args+=( --sandbox workspace-write )
    else
      args+=( --sandbox read-only )
    fi
    append_model_args args
    args+=( "$PROMPT" )
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  grok)
    append_grok_headless_args args "$PROMPT"
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  gemini)
    args=( -p "$PROMPT" --yolo --output-format json )
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  aider)
    args=( --message "$PROMPT" --yes-always )
    if [ "$MODE" = "smoke" ]; then
      args+=( --no-git )
    fi
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  hermes)
    # KANBAN_CODING_AGENT_CHILD=1 tells the coder profile that this is a
    # coding-agent child session — it should complete the task directly.
    export KANBAN_CODING_AGENT_CHILD=1
    args=( chat -q "$PROMPT" --yolo )
    if [[ -n "${PROFILE:-}" ]]; then
        args=( -p "${PROFILE}" "${args[@]}" )
    fi
    append_model_args args
    append_provider_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_hermes_and_meter "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;

  *)
    echo "[coding_agent_invoke] Unknown binary '$BINARY' — trying generic -p" >&2
    args=( -p "$PROMPT" )
    append_model_args args
    if [[ "$MODE" == "dispatch" ]]; then
      _dispatch_and_log "${args[@]}"
      exit $?
    fi
    exec "$BINARY" "${args[@]}"
    ;;
esac
