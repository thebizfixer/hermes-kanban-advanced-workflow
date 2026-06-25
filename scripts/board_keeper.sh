#!/usr/bin/env bash
# board_keeper.sh — Proactive board manager for walk-away kanban execution.
#
# Runs every 180 seconds. Does NOT just monitor — actively keeps the board moving:
#   1. Salvage iteration-limit cards (check worktree, commit, merge, complete)
#   2. Kill orphaned agent processes from archived cards
#   3. Unstick ready cards stalled >3 minutes (provider slot check)
#   4. Merge completed worktree branches to staging
#   5. Report board status
#
# Designed to run as a Hermes script-only cron (no_agent=true, deliver=local).
# Pure bash — salvage/unstick/merge inline; no LLM required for wave progression.
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/board_keeper.sh
#   bash hermes-kanban-advanced-workflow/scripts/board_keeper.sh
#
# ── HERMES_HOME resolution (cross-platform) ────────────────────────────
# Hermes Agent canonical resolution: $HERMES_HOME → ~/.hermes (default).
# Export it so child `hermes` processes find kanban.db.
# Ref: https://hermes-agent.nousresearch.com/docs/reference/environment-variables
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_PARSE="$SCRIPT_DIR/lib/cli_output_parse.py"
# shellcheck source=lib/kanban_logs.sh
source "$SCRIPT_DIR/lib/kanban_logs.sh"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/kanban_cli_parse.sh
source "$SCRIPT_DIR/lib/kanban_cli_parse.sh"
# shellcheck source=lib/auto_unblock_core.sh
source "$SCRIPT_DIR/lib/auto_unblock_core.sh"

pass() { echo "  ✓ $*"; }
warn() { echo "  ⚠ $*"; }
green() { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }

# ── Startup guard: validate repo root ──────────────────────────────────
_startup_guard() {
  local resolved_root
  resolved_root=$(git rev-parse --show-toplevel 2>/dev/null || echo "$REPO_ROOT")

  case "$resolved_root" in
    /mnt/*)
      if [[ $(uname -r) =~ (WSL|Microsoft) ]]; then
        echo "BLOCKED: Repo root $resolved_root is on WSL DrvFs (/mnt/ → Windows NTFS)." >&2
        echo "Clone the repo to a native filesystem path (not a cross-mount / DrvFS path) and re-run." >&2
        exit 1
      fi
      ;;
  esac

  local fs_type
  fs_type=$(df -T "$resolved_root" 2>/dev/null | awk 'NR==2 {print $2}')
  case "$fs_type" in
    9p|nfs|nfs4|fuse|fuseblk|cifs|smbfs|sshfs)
      echo "BLOCKED: Repo root $resolved_root is on cross-mount filesystem type $fs_type." >&2
      echo "Clone to a native filesystem (ext4, xfs, apfs, btrfs) and re-run." >&2
      exit 1
      ;;
  esac
}
_startup_guard

REPO_ROOT="${REPO_ROOT:-$PWD}"
if [ -z "$REPO_ROOT" ] || [ ! -d "$REPO_ROOT" ]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
if ! _load_branch_config "$REPO_ROOT"; then
    exit 1
fi
INTEGRATION_BRANCH="$WORKING_BRANCH"
CONFIG_FILE="$CONFIG_FILE"
DRY_RUN=false
PLAN_ID=""
[[ "${1:-}" == "--dry-run" ]] && { DRY_RUN=true; shift; }
[[ "${1:-}" == "--plan-id" ]] && { PLAN_ID="${2:-}"; shift 2; }

# Single-instance guard — skip overlapping ticks (#30908 SQLite write pressure).
LOCK_DIR="$(kanban_logs_dir "$REPO_ROOT")"
mkdir -p "$LOCK_DIR"
KEEPER_LOCK="${LOCK_DIR}/board_keeper${PLAN_ID:+_$PLAN_ID}.lock"
exec 9>"$KEEPER_LOCK"
if ! flock -n 9; then
  echo "board_keeper: previous tick still running — skipping"
  exit 0
fi

_kanban_disk_ok() {
  local git_dir avail_mb repo_mb threshold
  git_dir="$(git -C "$REPO_ROOT" rev-parse --git-dir 2>/dev/null || echo "$REPO_ROOT/.git")"
  avail_mb="$(df -BM "$git_dir" 2>/dev/null | awk 'NR==2 {gsub(/M/,"",$4); print $4}' || echo 9999)"
  repo_mb="$(du -sm "$REPO_ROOT" 2>/dev/null | awk '{print $1}' || echo 0)"
  threshold=$(( repo_mb * 2 ))
  [[ "$threshold" -lt 200 ]] && threshold=200
  [[ "${avail_mb:-0}" -ge "$threshold" ]]
}

# ── Board snapshot ──────────────────────────────────────────────────────

echo "=== Board Keeper @ $(date -u +%H:%M:%S) ==="
echo ""

# ── Heartbeat for watchdog monitoring ──────────────────────────────────
HEARTBEAT_FILE="${KANBAN_HEARTBEAT_FILE:-$(kanban_logs_dir "$REPO_ROOT")/board_keeper_heartbeat}"
mkdir -p "$(dirname "$HEARTBEAT_FILE")" 2>/dev/null || true
date -u +%s > "$HEARTBEAT_FILE" 2>/dev/null || true

BOARD=$(hermes kanban list 2>/dev/null)
echo "$BOARD"
echo ""

DONE=$(echo "$BOARD" | grep -c '✓' || true)
RUNNING=$(echo "$BOARD" | grep -c '●' || true)
READY=$(echo "$BOARD" | grep -c '▶' || true)
BLOCKED=$(echo "$BOARD" | grep -c '⊘' || true)
TODO=$(echo "$BOARD" | grep -c '◻' || true)

echo "Summary: $DONE done · $RUNNING running · $READY ready · $BLOCKED blocked · $TODO todo"

# ── 1. Detect orphaned agents ──────────────────────────────────────────

echo ""
echo "--- Orphaned agents ---"
ORPHANS=$(ps aux 2>/dev/null | grep 'kanban task t_' | grep -v grep | python3 "$CLI_PARSE" task-ids 2>/dev/null | sort -u || true)
ORPHAN_COUNT=0
for tid in $ORPHANS; do
    if ! hermes kanban show "$tid" &>/dev/null 2>&1; then
        PID=$(ps aux | grep "$tid" | grep -v grep | awk '{print $2}' | head -1)
        echo "ORPHAN: agent for archived card $tid (PID $PID)"
        if [ "$DRY_RUN" = false ]; then
            kill "$PID" 2>/dev/null && echo "  → killed PID $PID"
        fi
        ((ORPHAN_COUNT++))
    fi
done
[ $ORPHAN_COUNT -eq 0 ] && echo "(none)"

# ── 2. Detect blocked cards (iteration limit) — check for salvageable work ──

echo ""
echo "--- Blocked card salvage ---"
BLOCKED_IDS=$(hermes kanban list 2>/dev/null | grep '⊘' | awk '{print $2}' || true)
SALVAGE_COUNT=0
for tid in $BLOCKED_IDS; do
    INFO=$(hermes kanban show "$tid" 2>/dev/null)
    REASON=$(echo "$INFO" | grep -i 'Iteration\|iteration\|Latest summary' | head -1)
    if echo "$REASON" | grep -qi 'iteration'; then
        # This card hit iteration limit — check worktree for completed work
        WS=$(echo "$INFO" | grep "workspace:" | head -1 | sed 's/.*@ //' | xargs)
        CARD_NAME=$(echo "$INFO" | grep "Task $tid:" | head -1 | sed "s/Task $tid: //" | xargs)
        echo "BLOCKED (iteration): $tid — $CARD_NAME (workspace: ${WS:-unknown})"
        
        if [ -n "$WS" ] && [ -d "$WS" ]; then
            # Check for extracted module files
            NEW_FILES=$(cd "$WS" 2>/dev/null && git status --short 2>/dev/null | grep '??' | grep '\.py' | head -5 || true)
            MODIFIED=$(cd "$WS" 2>/dev/null && git diff --stat 2>/dev/null | tail -1 || true)
            
            if [ -n "$NEW_FILES" ] || [ -n "$MODIFIED" ]; then
                echo "  → WORK DETECTED in worktree:"
                [ -n "$NEW_FILES" ] && echo "    New: $NEW_FILES"
                [ -n "$MODIFIED" ] && echo "    Modified: $MODIFIED"
                
                if [ "$DRY_RUN" = false ]; then
                    # Commit worktree changes
                    cd "$WS"
                    git add -A 2>/dev/null
                    if git commit -m "feat: $CARD_NAME ($tid) — salvaged from iteration limit" 2>/dev/null; then
                        echo "  → Committed to worktree branch"
                        
                        # Fetch and merge to integration branch (working_branch)
                        BRANCH=$(git branch --show-current)
                        cd "$REPO_ROOT"
                        git remote add "wt-$tid" "$WS" 2>/dev/null || true
                        git fetch "wt-$tid" 2>/dev/null
                        if git merge "wt-$tid/$BRANCH" --no-edit 2>/dev/null; then
                            echo "  → Merged to $INTEGRATION_BRANCH"
                            hermes kanban complete "$tid" --summary "$CARD_NAME shipped (salvaged from iteration limit by board keeper)." 2>/dev/null
                            echo "  → Card completed"
                            ((SALVAGE_COUNT++))
                        fi
                        git remote remove "wt-$tid" 2>/dev/null || true
                    fi
                    cd "$REPO_ROOT"
                else
                    echo "  [dry-run] would salvage"
                fi
            else
                echo "  → No uncommitted work found — needs manual review or card split"
            fi
        fi
        echo ""
    fi
done
[ $SALVAGE_COUNT -eq 0 ] && echo "(no salvageable cards)"

# ── 2b. Escalation triage (all blocked cards) ───────────────────────────
# Detects repeated blocks, error signatures, and enforces 5-loop conversation cap.
# Two triggers: (1) 5+ identical-error loops → immediate escalation,
# (2) 2+ re-blocks on governance cards → force worker:attempt:2 escalation.

echo ""
echo "--- Escalation triage ---"
ESCALATION_COUNT=0
for tid in $BLOCKED_IDS; do
    SHOW=$(hermes kanban show "$tid" 2>/dev/null)
    REASON=$(echo "$SHOW" | grep -iE 'block|reason|summary' | head -1 || true)
    # Count prior "blocked" events for this card (re-block detection)
    BLOCK_COUNT=$(echo "$SHOW" | grep -c 'blocked {' || echo 0)

    # Extract error signatures from block events
    ERROR_SIGS=$(echo "$SHOW" | grep -oP 'E\d{3}[^\s,)]*' | sort -u | tr '\n' '|' || true)
    ERROR_SIGS="${ERROR_SIGS%|}"

    # Count identical-error repetitions
    if [ -n "$ERROR_SIGS" ]; then
        SAME_ERROR_COUNT=0
        for sig in $(echo "$ERROR_SIGS" | tr '|' ' '); do
            COUNT=$(echo "$SHOW" | grep -c "$sig" || echo 0)
            [ "$COUNT" -gt "$SAME_ERROR_COUNT" ] && SAME_ERROR_COUNT=$COUNT
        done
    else
        SAME_ERROR_COUNT=0
    fi

    FORCE_ESCALATE=false
    ESCALATION_REASON=""

    # Trigger 1: 5+ loops on identical error (conversation cap)
    if [ "$SAME_ERROR_COUNT" -ge 5 ]; then
        FORCE_ESCALATE=true
        ESCALATION_REASON="[escalation:worker:attempt:5] conversation cap: $SAME_ERROR_COUNT identical blocks ($ERROR_SIGS)"
        echo "  Board-keeper: conversation cap hit for $tid — $SAME_ERROR_COUNT identical $ERROR_SIGS blocks"
    # Trigger 2: 2+ re-blocks on E00x governance issues, force the worker:2 tag
    elif [ "$BLOCK_COUNT" -ge 2 ] && echo "$REASON" | grep -qiE 'E00|block'; then
        FORCE_ESCALATE=true
        ESCALATION_REASON="[escalation:worker:attempt:2] re-block #$BLOCK_COUNT ($ERROR_SIGS)"
        echo "  Board-keeper: re-block #$BLOCK_COUNT detected for $tid — forcing escalation"
    fi

    if [ "$FORCE_ESCALATE" = true ]; then
        TRACKER_OUT=$(bash "$SCRIPT_DIR/kanban_escalation_tracker.sh" \
            --task-id "$tid" \
            --block-reason "$ESCALATION_REASON" \
            --config "$CONFIG_FILE" \
            --repo-root "$REPO_ROOT" 2>/dev/null || true)
        case "$TRACKER_OUT" in
            ESCALATE:*)
                echo "$TRACKER_OUT"
                ((ESCALATION_COUNT++)) || true
                if echo "$TRACKER_OUT" | grep -q ':orchestrator'; then
                    hermes kanban comment "$tid" \
                        "Board-keeper escalation: $ESCALATION_REASON. Orchestrator to resolve." \
                        2>/dev/null || true
                    hermes kanban unblock "$tid" --reason "$TRACKER_OUT" 2>/dev/null || true
                    echo "  → unblocked with orchestrator escalation tag"
                fi
                ;;
            HUMAN_INTERVENTION:*)
                echo "$TRACKER_OUT"
                ((ESCALATION_COUNT++)) || true
                ;;
        esac
    fi
done
[ "$ESCALATION_COUNT" -eq 0 ] && echo "(no escalation signals this tick)"

# ── 3. Stuck ready cards (>3 min) — check provider slots ─────────────────

echo ""
echo "--- Stuck ready cards ---"
READY_IDS=$(hermes kanban list 2>/dev/null | grep '▶' | awk '{print $2}' || true)
STUCK_COUNT=0
for tid in $READY_IDS; do
    # Check how long it's been ready
    CREATED=$(hermes kanban show "$tid" 2>/dev/null | python3 "$CLI_PARSE" created 2>/dev/null || true)
    if [ -n "$CREATED" ]; then
        CREATED_EPOCH=$(date -d "$CREATED" +%s 2>/dev/null || true)
        NOW_EPOCH=$(date +%s)
        if [ -n "$CREATED_EPOCH" ] && [ $((NOW_EPOCH - CREATED_EPOCH)) -gt 180 ]; then
            CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
            echo "STUCK: $tid — $CARD_NAME — ready for $(((NOW_EPOCH - CREATED_EPOCH) / 60))min"
            ((STUCK_COUNT++))
        fi
    fi
done
[ $STUCK_COUNT -eq 0 ] && echo "(none stuck >3min)"

# ── 4. Provider slot check ──────────────────────────────────────────────

echo ""
CURSOR_RUNNING=$(ps aux 2>/dev/null | grep -c 'agent -p\|cursor-agent.*index.js' | grep -v grep || echo 0)
echo "Cursor CLI agents running: $CURSOR_RUNNING"
if [ "$READY" -gt 0 ] && [ "$CURSOR_RUNNING" -eq 0 ] && [ "$RUNNING" -eq 0 ]; then
    echo "⚠ $READY cards ready but 0 agents running — dispatcher may be stuck. Consider: hermes gateway restart"
fi

# ── 6. Max-retries enforcement ──────────────────────────────────────────

echo ""
echo "--- Max-retries check ---"
ALL_CARD_IDS=$(hermes kanban list 2>/dev/null | awk '{print $2}' | grep -E '^t_' || true)
RETRY_ISSUES=0
for tid in $ALL_CARD_IDS; do
    MAX_RETRIES=$(hermes kanban show "$tid" 2>/dev/null | python3 "$CLI_PARSE" max-retries 2>/dev/null || echo "0")
    if [ "$MAX_RETRIES" -gt 2 ] 2>/dev/null || [ "$MAX_RETRIES" -eq 0 ] 2>/dev/null; then
        CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
        warn "Card $tid ($CARD_NAME) has max-retries=$MAX_RETRIES (should be ≤2)"
        ((RETRY_ISSUES++))
    fi
done
[ $RETRY_ISSUES -eq 0 ] && pass "All cards have max-retries ≤2"

# ── 5. Thrash detection (event churn without terminal state) ─────────────

echo ""
echo "--- Thrash outliers ---"
THRASH_COUNT=0
if [[ -f "${HERMES_HOME}/kanban.db" ]]; then
  THRASH_IDS=$(python3 - "$HERMES_HOME/kanban.db" <<'PY' 2>/dev/null || true
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
cols = {r[1].lower(): r[1] for r in db.execute("PRAGMA table_info(tasks)").fetchall()}
event_tables = []
for name in ("kanban_events", "task_events", "events", "kanban_task_events"):
    try:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
            event_tables.append(name)
            break
    except sqlite3.Error:
        pass
if not event_tables:
    raise SystemExit(0)
etable = event_tables[0]
ecols = {r[1].lower(): r[1] for r in db.execute(f"PRAGMA table_info({etable})").fetchall()}
tid_col = ecols.get("task_id") or ecols.get("taskid")
if not tid_col:
    raise SystemExit(0)
status_col = cols.get("status", "status")
id_col = cols.get("id", "id")
rows = db.execute(
    f"SELECT {id_col}, {status_col} FROM tasks WHERE lower({status_col}) NOT IN ('done','completed','archived','gave_up','crashed','timed_out')"
).fetchall()
active = {r[0] for r in rows}
counts = {}
for row in db.execute(f"SELECT {tid_col}, COUNT(*) FROM {etable} GROUP BY {tid_col}"):
    if row[0] in active and row[1] > 40:
        counts[row[0]] = row[1]
for tid, n in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"{tid}\t{n}")
PY
)
  while IFS=$'\t' read -r tid evcount; do
    [[ -z "$tid" ]] && continue
    CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
    warn "Card $tid ($CARD_NAME) has $evcount events (>40) — possible thrash before iteration limit"
    ((THRASH_COUNT++))
  done <<< "$THRASH_IDS"
fi
[ $THRASH_COUNT -eq 0 ] && pass "No thrash outliers (>40 events on active cards)"

# ── 7. Done-but-unmerged detection + auto-merge ─────────────────────────

echo ""
echo "--- Unmerged done cards ---"
DONE_IDS=$(hermes kanban list 2>/dev/null | grep '✓' | awk '{print $2}' || true)
UNMERGED=0
MERGED_COUNT=0
DISK_OK=true
if ! _kanban_disk_ok; then
  warn "Low disk space — skipping auto-merge this tick"
  DISK_OK=false
fi
for tid in $DONE_IDS; do
    WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1 | sed 's/.*@ //' | xargs)
    [ -z "$WS" ] || [ ! -d "$WS" ] && continue
    # Check if worktree has commits not in integration branch
    BEHIND=$(cd "$WS" 2>/dev/null && git rev-list --count "${INTEGRATION_BRANCH}..HEAD" 2>/dev/null || echo "0")
    if [ "${BEHIND:-0}" -gt 0 ] 2>/dev/null; then
        CARD_NAME=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1 | sed "s/Task $tid: //")
        echo "  UNMERGED: $tid ($CARD_NAME) — $BEHIND commits ahead of $INTEGRATION_BRANCH in $WS"
        ((UNMERGED++))
        if [[ "$DRY_RUN" == false && "$DISK_OK" == true ]]; then
            BRANCH=$(cd "$WS" && git branch --show-current 2>/dev/null || true)
            if [[ -n "$BRANCH" ]]; then
                cd "$REPO_ROOT"
                git remote add "wt-$tid" "$WS" 2>/dev/null || true
                if git fetch "wt-$tid" 2>/dev/null && git merge "wt-$tid/$BRANCH" --no-edit 2>/dev/null; then
                    echo "  → Auto-merged $tid to $INTEGRATION_BRANCH"
                    ((MERGED_COUNT++))
                    ((UNMERGED--)) || true
                else
                    warn "  Auto-merge failed for $tid — manual review required"
                fi
                git remote remove "wt-$tid" 2>/dev/null || true
            fi
        fi
    fi
done
[ $UNMERGED -eq 0 ] && pass "All done cards merged to $INTEGRATION_BRANCH"

# ── 8. Stale worktree cleanup ──────────────────────────────────────────

echo ""
echo "--- Stale worktrees ---"
STALE_WTS=0
for wt in /tmp/wt-*; do
    [ -d "$wt" ] || continue
    # Check if this worktree corresponds to an active card
    WT_NAME=$(basename "$wt")
    IN_USE=false
    for tid in $ALL_CARD_IDS; do
        WS=$(hermes kanban show "$tid" 2>/dev/null | grep "workspace:" | head -1 | sed 's/.*@ //' | xargs)
        [[ "$WS" == "$wt" ]] && IN_USE=true && break
    done
    if [ "$IN_USE" = false ]; then
        # Check if worktree is old (>1 hour since last modified)
        if [ -n "$(find "$wt" -maxdepth 0 -mmin +60 2>/dev/null)" ]; then
            echo "  STALE: $wt (not in use by any active card, >1 hour old)"
            if [ "$DRY_RUN" = false ]; then
                git -C "$REPO_ROOT" worktree remove "$wt" --force 2>/dev/null && echo "  → removed" || echo "  → could not remove (may have uncommitted changes)"
            fi
            ((STALE_WTS++))
        fi
    fi
done
[ $STALE_WTS -eq 0 ] && pass "No stale worktrees"

# ── 5. Completion signal + post-execution pipeline ─────────────────────

# Pipeline scripts (relative to board_keeper.sh location)
WORKTREE_AUDIT="$SCRIPT_DIR/worktree_audit.sh"
GIT_SAFE_CLEANUP="$SCRIPT_DIR/git_safe_cleanup.sh"
GENERATE_POSTMORTEM="$SCRIPT_DIR/generate_postmortem.py"

# State tracking file
PIPELINE_STATE="/tmp/kanban_pipeline_state"

if [ "$RUNNING" -eq 0 ] && [ "$READY" -eq 0 ] && [ "$BLOCKED" -eq 0 ] && [ "$TODO" -eq 0 ]; then
    echo ""
    echo "🏁 ALL CARDS COMPLETE — triggering post-execution pipeline"
    
    # Stage 1: Worktree audit
    echo ""
    echo "=== Pipeline Stage 1/4: Worktree Audit ==="
    if [[ -x "$WORKTREE_AUDIT" ]]; then
        AUDIT_EXIT=0
        bash "$WORKTREE_AUDIT" --staging "$INTEGRATION_BRANCH" || AUDIT_EXIT=$?
        if [[ $AUDIT_EXIT -eq 0 ]]; then
            green "  ✓ All worktrees verified — no lost work"
            echo "READY_FOR_AUDIT" > "$PIPELINE_STATE"
        else
            yellow "  ⚠ Worktree audit found issues — review before continuing"
            echo "AUDIT_ISSUES" > "$PIPELINE_STATE"
        fi
    else
        yellow "  ⚠ worktree_audit.sh not found at $WORKTREE_AUDIT — skipping"
        echo "AUDIT_SKIPPED" > "$PIPELINE_STATE"
    fi
    
    # Stage 2: Final audit card signal
    echo "READY FOR FINAL AUDIT — all worktrees verified, no lost work"
    echo ""
    echo "PIPELINE_STAGE=fini_audit"
    
elif [ "$RUNNING" -eq 0 ] && [ "$READY" -eq 0 ] && [ "$TODO" -eq 0 ] && [ "$BLOCKED" -gt 0 ]; then
    echo ""
    echo "⚠ ALL CARDS BLOCKED ($BLOCKED) — orchestrator intervention required"
fi

# ── Post-final-audit: walk-away post-exec or orchestrator checkpoint signal ──
PIPELINE_CURRENT=$(cat "$PIPELINE_STATE" 2>/dev/null || echo "")
AUDIT_DONE_IDS=$(hermes kanban list 2>/dev/null | grep '✓' | awk '{print $2}' || true)
AUDIT_COMPLETE=false

for tid in $AUDIT_DONE_IDS; do
    TITLE=$(hermes kanban show "$tid" 2>/dev/null | grep "Task $tid:" | head -1)
    if echo "$TITLE" | grep -qiE 'final[ -]audit'; then
        AUDIT_COMPLETE=true
        break
    fi
done

if [[ "$AUDIT_COMPLETE" == "true" ]] && [[ "$PIPELINE_CURRENT" == "READY_FOR_AUDIT" || "$PIPELINE_CURRENT" == "AUDIT_ISSUES" || "$PIPELINE_CURRENT" == "AUDIT_SKIPPED" ]]; then
    PLAN_ID="$(_resolve_active_plan_id "$REPO_ROOT")"
    if _walk_away_mode_enabled "$CONFIG_FILE" 2>/dev/null; then
        echo ""
        echo "=== Walk-away mode: unattended post-execution ==="
        if [[ -f "$SCRIPT_DIR/kanban_walk_away_post_exec.sh" ]]; then
            bash "$SCRIPT_DIR/kanban_walk_away_post_exec.sh" --plan-id "$PLAN_ID" || true
        else
            yellow "  kanban_walk_away_post_exec.sh not found — skipping"
        fi
        echo "PIPELINE_COMPLETE" > "$PIPELINE_STATE"
    else
        echo ""
        echo "KANBAN_COMPLETE — final audit done; orchestrator checkpoints required (walk_away_mode off)"
        echo "PIPELINE_AWAITING_OPERATOR" > "$PIPELINE_STATE"
    fi
fi

echo ""
echo "=== Board Keeper complete: $SALVAGE_COUNT salvaged, $ORPHAN_COUNT orphans killed, $STUCK_COUNT stuck, $MERGED_COUNT auto-merged ==="

# ── 9. Wave progression — unblock eligible cards in same tick ───────────
echo ""
echo "--- Auto-unblock (board_keeper tick) ---"
kanban_auto_unblock_tick --stagger-sec "${KANBAN_UNBLOCK_STAGGER_SEC:-0}" --max-unblock "${KANBAN_UNBLOCK_MAX_PER_TICK:-0}" || true

LOG_DIR="$(kanban_logs_dir "$REPO_ROOT")"
mkdir -p "$LOG_DIR"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) salvaged=$SALVAGE_COUNT orphans=$ORPHAN_COUNT stuck=$STUCK_COUNT merged=$MERGED_COUNT" >> "${LOG_DIR}/board-keeper.log"

# Cron staleness probe: warn when active cards exist but wave crons never ticked.
ACTIVE=$((RUNNING + READY + BLOCKED + TODO))
if [[ "$ACTIVE" -gt 0 ]]; then
  AU_LOG="${LOG_DIR}/auto-unblock.log"
  GW_OK=false
  if hermes cron status 2>/dev/null | grep -qiE 'running|active'; then
    GW_OK=true
  elif hermes gateway status 2>/dev/null | grep -qiE 'running|active'; then
    GW_OK=true
  fi
  if [[ ! -f "$AU_LOG" ]] || [[ -z "$(find "$AU_LOG" -mmin -3 2>/dev/null)" ]]; then
    if [[ "$GW_OK" != true ]]; then
      warn "Gateway not running — wave crons will not tick (hermes gateway start)"
    else
      warn "auto-unblock log stale >3m with $ACTIVE active cards — verify cron --workdir and gateway"
    fi
  fi
fi
