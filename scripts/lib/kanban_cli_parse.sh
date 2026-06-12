#!/usr/bin/env bash
# Portable parsers for hermes kanban CLI output (GNU + BSD grep; no grep -P).
#
# Usage (after sourcing):
#   echo "$detail" | kanban_extract_task_ids
#   echo "$line" | kanban_extract_first_number

kanban_extract_task_ids() {
  grep -oE 't_[[:alnum:]_]+' 2>/dev/null || true
}

kanban_extract_first_number() {
  grep -oE '[0-9]+' 2>/dev/null | head -1 || true
}
