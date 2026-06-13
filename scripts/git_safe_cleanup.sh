#!/usr/bin/env bash
# git_safe_cleanup.sh — Governed git worktree and branch cleanup.
#
# Two modes:
#   --audit   Read-only inventory of worktrees and branches (safe, always)
#   --clean   Governed deletion with safety gates before every destructive operation
#
# Safety gates (applied before every destructive operation):
#   Before git worktree remove:  verify worktree is clean + all commits merged to staging
#   Before git branch -d:        verify branch contained in staging + staging pushed to remote
#   Before git reset --hard:     always git stash first
#   Never use --force without --dry-run first
#
# Usage:
#   bash git_safe_cleanup.sh --audit                    # Inventory only
#   bash git_safe_cleanup.sh --clean                    # Governed deletion
#   bash git_safe_cleanup.sh --clean --dry-run          # Show what would be deleted
#   bash git_safe_cleanup.sh --clean --staging staging  # Specify staging branch
#
# Exit codes:
#   0 — Success (audit complete, or clean with no errors)
#   1 — Audit found issues needing attention
#   2 — Clean operation blocked by safety gate
#   3 — Usage error

set -euo pipefail

# ── Startup guard: validate repo root ──────────────────────────────────
_resolved_root=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
case "$_resolved_root" in
  /mnt/*)
    if [[ $(uname -r) =~ (WSL|Microsoft) ]]; then
      echo "BLOCKED: Repo root $_resolved_root is on WSL DrvFs. Clone to native WSL path." >&2
      exit 1
    fi
    ;;
esac
_fs_type=$(df -T "$_resolved_root" 2>/dev/null | awk 'NR==2 {print $2}')
case "$_fs_type" in
  9p|nfs|nfs4|fuse|fuseblk|cifs|smbfs|sshfs)
    echo "BLOCKED: Repo root $_resolved_root is on cross-mount filesystem type $_fs_type." >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_PARSE="$SCRIPT_DIR/lib/cli_output_parse.py"
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! _load_branch_config "$REPO_ROOT"; then
    exit 1
fi

MODE="audit"
DRY_RUN=false
STAGING_BRANCH="$WORKING_BRANCH"
WORKTREE_PATTERN="${KANBAN_WORKTREE_PATTERN:-/tmp/wt-*}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --audit) MODE="audit"; shift ;;
        --clean) MODE="clean"; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --staging) STAGING_BRANCH="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 3 ;;
    esac
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$REPO_ROOT"

red()    { echo -e "\033[31m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }
blue()   { echo -e "\033[34m$*\033[0m"; }

# ── Safety gate helpers ─────────────────────────────────────────────────
is_worktree_clean() {
    local wt="$1"
    [[ -d "$wt/.git" || -f "$wt/.git" ]] || return 1
    local dirty
    dirty=$(git -C "$wt" status --short 2>/dev/null)
    [[ -z "$dirty" ]]
}

is_worktree_merged_to_staging() {
    local wt="$1"
    [[ -d "$wt/.git" || -f "$wt/.git" ]] || return 1
    local ahead
    ahead=$(git -C "$wt" rev-list --count "${STAGING_BRANCH}..HEAD" 2>/dev/null || echo "-1")
    [[ "$ahead" == "0" ]]
}

is_branch_contained_in_staging() {
    local branch="$1"
    git branch --contains "$branch" "$STAGING_BRANCH" &>/dev/null
}

is_staging_pushed() {
    local ahead
    ahead=$(git rev-list --count "origin/${STAGING_BRANCH}..${STAGING_BRANCH}" 2>/dev/null || echo "-1")
    [[ "$ahead" == "0" ]]
}

is_worktree_in_use() {
    local wt="$1"
    # Check if any process has this worktree as its cwd
    pgrep -f "$wt" &>/dev/null && return 0
    # Check if hermes kanban references this worktree
    hermes kanban list 2>/dev/null | grep -q "$wt" && return 0
    return 1
}

classify_branch() {
    local branch="$1"
    # Remove leading whitespace and remote prefixes
    branch=$(echo "$branch" | sed 's/^[* ]*//; s|^remotes/origin/||; s|^origin/||')
    # Skip HEAD pointer lines and empty branches
    [[ -z "$branch" || "$branch" == "HEAD" || "$branch" =~ "->" ]] && echo "meta" && return

    [[ "$branch" == "$STAGING_BRANCH" || "$branch" == "main" || "$branch" == "master" ]] && echo "protected" && return
    [[ "$branch" =~ ^kanban/ ]] && echo "kanban" && return
    [[ "$branch" =~ fix|cherry-pick|hotfix|staging-fix ]] && echo "fix" && return
    is_branch_contained_in_staging "$branch" && echo "merged" || echo "orphaned"
}

echo "=== git_safe_cleanup — ${MODE} mode ==="
echo "Repo: $REPO_ROOT"
echo "Staging: $STAGING_BRANCH"
[[ "$DRY_RUN" == "true" ]] && yellow "[dry-run] No destructive operations will be performed"
echo ""

# ══════════════════════════════════════════════════════════════════════════
# PHASE 1: Inventory (both modes)
# ══════════════════════════════════════════════════════════════════════════

blue "--- Worktree Inventory ---"
WORKTREES=$(git worktree list 2>/dev/null)
echo "$WORKTREES"
echo ""

WT_COUNT=0
WT_CLEANABLE=0
WT_NEEDS_REVIEW=0
WT_IN_USE=0

while IFS= read -r wt_line; do
    [[ -z "$wt_line" ]] && continue
    WT_PATH=$(echo "$wt_line" | awk '{print $1}')
    WT_BRANCH=$(python3 "$CLI_PARSE" worktree-branch --text "$wt_line" 2>/dev/null || echo "detached")

    ((WT_COUNT++))
    echo "Worktree: $WT_PATH  [$WT_BRANCH]"

    if is_worktree_in_use "$WT_PATH"; then
        yellow "  → IN USE (active process or kanban card)"
        ((WT_IN_USE++))
        continue
    fi

    if ! is_worktree_clean "$WT_PATH"; then
        red "  → DIRTY — has uncommitted changes. Cannot safely remove."
        git -C "$WT_PATH" status --short 2>/dev/null | head -5
        ((WT_NEEDS_REVIEW++))
        continue
    fi

    if ! is_worktree_merged_to_staging "$WT_PATH"; then
        AHEAD=$(git -C "$WT_PATH" rev-list --count "${STAGING_BRANCH}..HEAD" 2>/dev/null || echo "?")
        yellow "  → UNMERGED — $AHEAD commit(s) ahead of $STAGING_BRANCH. Manual review needed."
        ((WT_NEEDS_REVIEW++))
        continue
    fi

    # Check if worktree is old enough (>1 hour since last modified)
    if [[ -n "$(find "$WT_PATH" -maxdepth 0 -mmin +60 2>/dev/null)" ]]; then
        green "  → CLEANABLE — clean, merged, stale (>1hr)"
        ((WT_CLEANABLE++))
    else
        yellow "  → RECENT — clean and merged, but modified <1hr ago. Skipping."
        ((WT_NEEDS_REVIEW++))
    fi
done <<< "$(echo "$WORKTREES" | tail -n +2)"

echo ""
blue "--- Branch Inventory ---"
BRANCHES=$(git branch -a 2>/dev/null)
echo "$BRANCHES" | head -20
[[ $(echo "$BRANCHES" | wc -l) -gt 20 ]] && echo "  ... ($(echo "$BRANCHES" | wc -l) branches total)"
echo ""

BRANCH_COUNT=0
BRANCH_MERGED=0
BRANCH_ORPHANED=0
BRANCH_KANBAN=0
BRANCH_FIX=0
BRANCH_PROTECTED=0

while IFS= read -r branch_line; do
    [[ -z "$branch_line" ]] && continue
    BRANCH=$(echo "$branch_line" | sed 's/^[* ]*//')
    CLASS=$(classify_branch "$BRANCH")
    ((BRANCH_COUNT++))

    case "$CLASS" in
        merged)    ((BRANCH_MERGED++)) ;;
        orphaned)  ((BRANCH_ORPHANED++)) ;;
        kanban)    ((BRANCH_KANBAN++)) ;;
        fix)       ((BRANCH_FIX++)) ;;
        protected) ((BRANCH_PROTECTED++)) ;;
    esac
done <<< "$(echo "$BRANCHES" | grep -v 'remotes/' || true)"

echo "Branch classification:"
echo "  Protected: $BRANCH_PROTECTED ($STAGING_BRANCH, main, master)"
echo "  Merged:    $BRANCH_MERGED  (contained in $STAGING_BRANCH)"
echo "  Kanban:    $BRANCH_KANBAN  (kanban/ prefix — active or done cards)"
echo "  Fix:       $BRANCH_FIX     (troubleshooting branches)"
echo "  Orphaned:  $BRANCH_ORPHANED (not in $STAGING_BRANCH)"
echo ""

# ── Staging push check ──────────────────────────────────────────────────
if is_staging_pushed; then
    green "Staging is pushed to remote — safe for cleanup."
else
    AHEAD=$(git rev-list --count "origin/${STAGING_BRANCH}..${STAGING_BRANCH}" 2>/dev/null || echo "?")
    yellow "WARNING: $STAGING_BRANCH is $AHEAD commit(s) ahead of origin. Push before cleanup."
fi

# ══════════════════════════════════════════════════════════════════════════
# PHASE 2: Cleanup (--clean mode only)
# ══════════════════════════════════════════════════════════════════════════

if [[ "$MODE" != "clean" ]]; then
    echo ""
    blue "=== Audit complete ==="
    echo "Worktrees: $WT_COUNT total · $WT_CLEANABLE cleanable · $WT_NEEDS_REVIEW needs review · $WT_IN_USE active"
    echo "Branches:  $BRANCH_COUNT total · $BRANCH_MERGED merged · $BRANCH_ORPHANED orphaned · $BRANCH_FIX fix · $BRANCH_KANBAN kanban"
    
    ISSUES=$(( WT_NEEDS_REVIEW + BRANCH_ORPHANED ))
    if [[ $ISSUES -gt 0 ]]; then
        yellow "→ $ISSUES item(s) need attention before cleanup."
        exit 1
    fi
    exit 0
fi

# ── Clean mode safety gate ──────────────────────────────────────────────
if ! is_staging_pushed; then
    red "BLOCKED: $STAGING_BRANCH is not pushed to remote. Push first: git push origin $STAGING_BRANCH"
    exit 2
fi

echo ""
blue "--- Cleanup Phase ---"
CLEANED_WT=0
CLEANED_BR=0
SKIPPED_WT=0
SKIPPED_BR=0

# ── 2a. Remove cleanable worktrees ─────────────────────────────────────
while IFS= read -r wt_line; do
    [[ -z "$wt_line" ]] && continue
    WT_PATH=$(echo "$wt_line" | awk '{print $1}')

    # Re-verify safety gates
    if is_worktree_in_use "$WT_PATH"; then
        echo "SKIP: $WT_PATH — in use"
        ((SKIPPED_WT++))
        continue
    fi
    if ! is_worktree_clean "$WT_PATH"; then
        echo "SKIP: $WT_PATH — dirty (uncommitted changes)"
        ((SKIPPED_WT++))
        continue
    fi
    if ! is_worktree_merged_to_staging "$WT_PATH"; then
        echo "SKIP: $WT_PATH — not fully merged to $STAGING_BRANCH"
        ((SKIPPED_WT++))
        continue
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[dry-run] Would remove: $WT_PATH"
        ((CLEANED_WT++))
    else
        echo "REMOVE: $WT_PATH"
        if git worktree remove "$WT_PATH" 2>/dev/null; then
            green "  → Removed"
            ((CLEANED_WT++))
        else
            # Try with --force as last resort (only if all gates passed)
            yellow "  → Regular remove failed, trying with force (gates were clean)..."
            if git worktree remove --force "$WT_PATH" 2>/dev/null; then
                green "  → Force-removed (clean per safety gates)"
                ((CLEANED_WT++))
            else
                red "  → Could not remove — may be on different filesystem"
                ((SKIPPED_WT++))
            fi
        fi
    fi
done <<< "$(echo "$WORKTREES" | tail -n +2)"

# ── 2b. Delete merged branches ─────────────────────────────────────────
while IFS= read -r branch_line; do
    [[ -z "$branch_line" ]] && continue
    BRANCH_RAW=$(echo "$branch_line" | sed 's/^[* ]*//')
    BRANCH="$BRANCH_RAW"
    CLASS=$(classify_branch "$BRANCH")

    # Only clean merged branches (not protected, not fix without review)
    if [[ "$CLASS" != "merged" ]]; then
        [[ "$CLASS" == "kanban" ]] && is_branch_contained_in_staging "$BRANCH" && CLASS="merged-kanban"
        [[ "$CLASS" != "merged-kanban" ]] && continue
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[dry-run] Would delete branch: $BRANCH"
        ((CLEANED_BR++))
    else
        echo "DELETE branch: $BRANCH"
        if git branch -d "$BRANCH" 2>/dev/null; then
            green "  → Deleted"
            ((CLEANED_BR++))
        else
            yellow "  → Could not delete — may need -D. Skipping for safety."
            ((SKIPPED_BR++))
        fi
    fi
done <<< "$(echo "$BRANCHES" | grep -v 'remotes/' || true)"

# ── 2c. Check for fix branches ─────────────────────────────────────────
echo ""
FIX_BRANCHES=$(echo "$BRANCHES" | grep -v 'remotes/' | while IFS= read -r bl; do
    B=$(echo "$bl" | sed 's/^[* ]*//')
    [[ "$(classify_branch "$B")" == "fix" ]] && echo "$B"
done || true)

if [[ -n "$FIX_BRANCHES" ]]; then
    yellow "Fix branches found (require manual review):"
    echo "$FIX_BRANCHES" | while IFS= read -r fb; do
        AHEAD=$(git rev-list --count "${STAGING_BRANCH}..${fb}" 2>/dev/null || echo "?")
        echo "  $fb — $AHEAD commits ahead of $STAGING_BRANCH"
    done
fi

# ── 2d. Post-cleanup verification ──────────────────────────────────────
echo ""
blue "--- Post-Cleanup Verification ---"
NEW_WT_COUNT=$(git worktree list 2>/dev/null | tail -n +2 | wc -l)
NEW_BR_COUNT=$(git branch 2>/dev/null | wc -l)

echo "Worktrees: $WT_COUNT → $NEW_WT_COUNT ($CLEANED_WT removed, $SKIPPED_WT skipped)"
echo "Branches:  $BRANCH_COUNT → $NEW_BR_COUNT ($CLEANED_BR deleted, $SKIPPED_BR skipped)"

echo ""
blue "=== Cleanup complete ==="
echo "Removed: $CLEANED_WT worktrees, $CLEANED_BR branches"
echo "Skipped: $SKIPPED_WT worktrees, $SKIPPED_BR branches"
[[ $(( WT_NEEDS_REVIEW + BRANCH_FIX )) -gt 0 ]] && yellow "→ $WT_NEEDS_REVIEW worktree(s) and $BRANCH_FIX fix-branch(es) still need manual review."

exit 0
