#!/usr/bin/env bash
# coding_agent_invoke.sh — headless smoke or dispatch for KANBAN_CODING_AGENT
#
# Usage:
#   coding_agent_invoke.sh smoke
#   coding_agent_invoke.sh dispatch "<full prompt>"
#
# Env:
#   KANBAN_CODING_AGENT        (default: agent)
#   KANBAN_CODING_AGENT_MODEL  (default: auto)
set -euo pipefail

MODE="${1:-smoke}"
PROMPT="${2:-say ok}"
BINARY="${KANBAN_CODING_AGENT:-agent}"
MODEL="${KANBAN_CODING_AGENT_MODEL:-auto}"

model_is_auto() {
  case "${MODEL,,}" in
    ""|auto|default) return 0 ;;
    *) return 1 ;;
  esac
}

append_model_args() {
  local -n _out=$1
  if model_is_auto; then
    return 0
  fi
  case "$BINARY" in
    codex)
      _out+=(--model "$MODEL")
      ;;
    grok)
      _out+=(--model "$MODEL")
      ;;
    aider)
      _out+=(--model "$MODEL")
      ;;
    *)
      _out+=(--model "$MODEL")
      ;;
  esac
}

case "$BINARY" in
  agent)
    # Cursor: -p = --print; --output-format requires -p; --trust required in worktrees
    args=( -p "$PROMPT" --output-format json --trust )
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
  claude)
    args=( -p "$PROMPT" --output-format json --dangerously-skip-permissions )
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
  codex)
    args=( exec --json -a never )
    if [ "$MODE" = "dispatch" ]; then
      args+=( --sandbox workspace-write )
    fi
    append_model_args args
    args+=( "$PROMPT" )
    exec "$BINARY" "${args[@]}"
    ;;
  grok)
    args=( --prompt "$PROMPT" --format json )
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
  gemini)
    args=( --yolo --output-format json "$PROMPT" )
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
  aider)
    args=( --message "$PROMPT" --yes-always )
    if [ "$MODE" = "smoke" ]; then
      args+=( --no-git )
    fi
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
  *)
  echo "[coding_agent_invoke] Unknown binary '$BINARY' — trying generic -p" >&2
    args=( -p "$PROMPT" )
    append_model_args args
    exec "$BINARY" "${args[@]}"
    ;;
esac
