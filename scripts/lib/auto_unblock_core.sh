# shellcheck shell=bash
# auto_unblock_core.sh — shared unblock logic for auto_unblock.sh and board_keeper.sh
#
# Usage (after sourcing kanban_cli_parse.sh):
#   source "$SCRIPT_DIR/lib/auto_unblock_core.sh"
#   kanban_auto_unblock_tick [--dry-run] [--max-unblock N]

kanban_card_gave_up() {
  local tid="$1"
  local detail status summary
  detail="$(hermes kanban show "$tid" 2>/dev/null || true)"
  [[ -z "$detail" ]] && return 1
  status="$(echo "$detail" | grep -E '^status:' | head -1 | awk '{print $2}' || true)"
  summary="$(echo "$detail" | grep -iE 'gave_up|gave up|failure.?limit|iteration limit' | head -1 || true)"
  if [[ "$status" == "gave_up" ]]; then
    return 0
  fi
  if echo "$summary" | grep -qiE 'gave_up|gave up|failure.?limit|iteration limit'; then
    return 0
  fi
  return 1
}

_has_active_remediation_children() {
  local audit_tid="$1"
  local child detail status
  local children=""
  children="$(hermes kanban list --parent "$audit_tid" 2>/dev/null | awk '/^t_/ {print $1}' || true)"
  local used_parent_list=false
  if [[ -n "$children" ]]; then
    used_parent_list=true
  else
    children="$(hermes kanban list 2>/dev/null | awk '/^t_/ {print $1}' || true)"
  fi
  for child in $children; do
    detail="$(hermes kanban show "$child" 2>/dev/null || true)"
    [[ -z "$detail" ]] && continue
    echo "$detail" | grep -qiE 'Type:[[:space:]]*remediation' || continue
    if [[ "$used_parent_list" != true ]]; then
      echo "$detail" | grep -q "$audit_tid" || continue
    fi
    status="$(echo "$detail" | grep -E '^status:' | head -1 | awk '{print $2}' || true)"
    if [[ "$status" == "running" || "$status" == "ready" || "$status" == "blocked" ]]; then
      return 0
    fi
  done
  return 1
}

kanban_auto_unblock_tick() {
  local dry_run=false
  local max_unblock=0
  local stagger_sec="${KANBAN_UNBLOCK_STAGGER_SEC:-0}"
  local json_out=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=true; shift ;;
      --json) json_out=true; shift ;;
      --stagger-sec) stagger_sec="${2:-0}"; shift 2 ;;
      --max-unblock) max_unblock="${2:-0}"; shift 2 ;;
      *) shift ;;
    esac
  done

  local unblocked=0 skipped=0 errors=0
  local blocked_list
  blocked_list="$(hermes kanban list 2>/dev/null | grep '⊘' | awk '{print $2}' || true)"

  if [[ -z "$blocked_list" ]]; then
    if [[ "$json_out" == true ]]; then
      echo '{"unblocked":0,"skipped":0,"errors":0,"message":"no blocked cards"}'
    fi
    return 0
  fi

  for tid in $blocked_list; do
    if kanban_card_gave_up "$tid"; then
      ((skipped++)) || true
      continue
    fi

    local detail parents all_done=true pstatus
    detail="$(hermes kanban show "$tid" 2>/dev/null || true)"
    if [[ -z "$detail" ]]; then
      ((errors++)) || true
      continue
    fi

    parents="$(echo "$detail" | grep "parents:" | kanban_extract_task_ids)"
    if [[ -z "$parents" ]]; then
      ((skipped++)) || true
      continue
    fi

    all_done=true
    for pid in $parents; do
      pstatus="$(hermes kanban show "$pid" 2>/dev/null | grep "status:" | head -1 | awk '{print $2}' || true)"
      if [[ "$pstatus" != "done" ]]; then
        all_done=false
        break
      fi
    done

    if [[ "$all_done" != true ]]; then
      ((skipped++)) || true
      continue
    fi

    if echo "$detail" | grep -qiE 'Type:[[:space:]]*audit' && _has_active_remediation_children "$tid"; then
      ((skipped++)) || true
      continue
    fi

    if [[ "$dry_run" == true ]]; then
      ((unblocked++)) || true
      continue
    fi

    if hermes kanban unblock "$tid" 2>/dev/null; then
      ((unblocked++)) || true
      if [[ "$stagger_sec" =~ ^[0-9]+$ && "$stagger_sec" -gt 0 ]]; then
        sleep "$stagger_sec"
      fi
      if [[ "$max_unblock" -gt 0 && "$unblocked" -ge "$max_unblock" ]]; then
        break
      fi
    else
      ((errors++)) || true
    fi
  done

  if [[ "$json_out" == true ]]; then
    echo "{\"unblocked\":$unblocked,\"skipped\":$skipped,\"errors\":$errors}"
  else
    echo "auto_unblock: unblocked=$unblocked skipped=$skipped errors=$errors stagger=${stagger_sec}"
  fi
  return 0
}
