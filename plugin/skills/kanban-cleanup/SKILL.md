---
name: kanban-cleanup
description: Post-plan cleanup — postmortem report, archive tasks, remove crons, kill tmux sessions, stage non-kanban changes.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, cleanup, devops, postmortem]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-postmortem, kanban-advanced:kanban-notify]
---

# Kanban Cleanup

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Run after reconciliation. Generates the postmortem retrospective, then removes all kanban runtime artifacts and prepares the repo for the next plan.

**Order is mandatory:** generate postmortem while task history and token logs are still intact, then archive the board. Do not archive tasks before the postmortem file exists.

## Cleanup steps

### 0. Generate postmortem report

Resolve `plan_id` from the plan file (`plan_id:` in frontmatter), `HERMES_KANBAN_PLAN_ID`, or the final-audit card body. Run the generator **before** any `hermes kanban archive`:

```bash
PLAN_ID="${HERMES_KANBAN_PLAN_ID:-<plan-id>}"
python hermes-kanban-advanced-workflow/scripts/generate_postmortem.py \
  --plan-id "$PLAN_ID" \
  --output .hermes/kanban/reports/
```

The script reads token JSONL (`KANBAN_TOKEN_LOG` or `~/.hermes/kanban/tokens.jsonl`), task history from the kanban SQLite DB (`KANBAN_DB` or `~/.hermes/state.db`), and the intervention counter. It writes an eight-section markdown report (execution summary, agent performance, failure taxonomy, intervention log, discovered pitfalls, skill updates, token economics, learning summary). Confirm stdout shows `Postmortem written: ...` before proceeding.

Cross-reference: `kanban-advanced:kanban-postmortem` skill for section semantics; `generate_postmortem.py` for flags (`--token-log`, `--db`, `--stdout`).

**If postmortem shows `uncaught_violation_count: null` or WARN for missing tier JSON:** final audit did not complete or tier JSON was deleted — re-run `final_audit_sanity.py --tier all` before archive. Load `kanban-advanced:kanban-postmortem` § Final audit KPIs.

### 1. Archive all kanban tasks

**Only after Step 0 succeeds.**

```bash
hermes kanban archive <task_id>  # repeat for each task
# Verify: hermes kanban list should show "(no matching tasks)"
```

### 2. Remove wave crons (mandatory) + optional monitor cron
```bash
PLAN_ID="${HERMES_KANBAN_PLAN_ID:-<plan-id>}"
bash hermes-kanban-advanced-workflow/scripts/provision_kanban_crons.sh --remove --plan-id "$PLAN_ID"
# Optional walk-away monitor (separate from wave crons):
cronjob(action="list")  # find kanban-monitor job if created
cronjob(action="remove", job_id="<id>")
```

### 3. Kill tmux watch session
```bash
tmux kill-session -t kanban-watch 2>/dev/null
```

### 4. Kill orphaned agent processes
```bash
ps aux | grep "agent -p" | grep -v grep
# Kill any that outlived their workers
```

### 5. Stage non-kanban changes
```bash
git status --short
# Stage only project files — NEVER stage `.hermes/` or vendor IDE artifact directories
git add <specific files>
# Do NOT use git add -A
```

### 6. Remove stale git locks
```bash
find . -name 'index.lock' -mmin +30 -delete 2>/dev/null
```

### 7. Verify board is empty
```bash
hermes kanban list
# Should show "(no matching tasks)"
```

## Completion notification opt-in

**Off by default.** Walk-away runs stay silent on plan completion unless the operator opts in.

| Variable | Default | When `true` |
| --- | --- | --- |
| `NOTIFY_ON_COMPLETE` | unset / `false` | After **postmortem generation (Step 0)** and **board archive (Step 1)**, send a non-intervention summary via the Hermes gateway operator chat |

```bash
export NOTIFY_ON_COMPLETE=true
```

Completion message (no intervention prefix — see `kanban-advanced:kanban-notify`):

```text
✅ Kanban plan complete — {plan_id}

{done} tasks done · postmortem: .hermes/kanban/reports/{plan_id}_postmortem_{date}.md
Board archived. Review postmortem when back.
```

Prerequisites: gateway running and chat channel configured (`kanban-advanced:kanban-notify` § Gateway delivery setup). CLI-only environments should skip gateway send and rely on the written postmortem path printed by Step 0.

## Git-safe cleanup scripts

Two governed scripts handle post-execution git hygiene. Always run these rather than manually deleting worktrees or branches — the safety gates prevent accidental loss of uncommitted or unmerged work.

### `git_safe_cleanup.sh`

Two modes:
- **`--audit`** — Read-only inventory of all worktrees and branches. Classifies each: protected, merged, kanban, fix, orphaned. Verifies `${working_branch}` is pushed to remote. Exit 1 if issues found.
- **`--clean`** — Governed deletion. Every destructive operation gated: before `git worktree remove`, checks cleanliness and merge status; before `git branch -d`, verifies branch contained in `${working_branch}` AND `${working_branch}` pushed. Never `--force` without `--dry-run` first.

### `worktree_audit.sh`

Cross-references `git worktree list` with `hermes kanban list`. Classifies each worktree: safe-to-clean (done + merged), needs-salvage (done + unmerged), potential-loss (no card + dirty), stale (no card + clean >1hr). Exit 1 if any worktree needs attention.

### Do not manually clean up

After building these scripts, **use them** — don't fall back to manual `git worktree remove --force` or `git branch -D`. The governance exists because manual cleanup loses work. If a script has a bug, fix the script, then use it.

## What NOT to clean up

- `.hermes/skills/` — updated skills should be committed
- `.hermes/SOUL.md` — identity updates should be committed
- Plan files (`.agent/plans/`) — preserved for audit trail
- Postmortem reports (`.hermes/kanban/reports/`) — preserved for the next plan's learning pass
- Git branches — the orchestrator handles merge

## Pitfalls

**`git branch -a` produces empty branch names.** `remotes/origin/HEAD -> origin/main` lines become empty strings after `sed 's|^remotes/origin/||'`. When passed to `git branch --contains ""` under `set -euo pipefail`, the script exits silently with no output. Guard `classify_branch()`: skip empty strings and lines containing `->` before calling any git command.

**`${working_branch}` locked by stale worktree.** When `${working_branch}` is checked out in a leftover worktree, you cannot `git checkout ${working_branch}` from the main repo. Remove the stale worktree first (`git worktree remove --force` only after verifying no uncommitted work), then update the local ref.

**Re-install after skill changes.** After editing skill files under `plugin/skills/`, re-install the plugin to pick up changes. The agent loads skills from the plugin directory.
