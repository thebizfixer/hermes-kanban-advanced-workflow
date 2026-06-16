---
name: kanban-git
description: Governed git operations for kanban card worktrees — setup, parent integration, plan restore, freshness checks. Load before worker Step 3 when cards reference parent branches.
---

# kanban-git

Thin router to governed scripts. **Never** run raw `git worktree add` or hand-typed parent merges.

## Mandatory

- Worktree create: `bash scripts/kanban_git_ops.sh setup --task-id "$TASK_ID" --repo-root "$REPO_ROOT"`
- Parent integration: `bash scripts/kanban_git_ops.sh integrate --task-id "$TASK_ID" --parent-keys card2,card5`
- Plan restore: `bash scripts/kanban_git_ops.sh restore-plan --plan-id "$PLAN_ID" --worktree "$WORKTREE"`
- Freshness: `bash scripts/kanban_git_ops.sh freshness --worktree "$WORKTREE"`

## Forbidden

- `git push` to `${working_branch}`
- `git reset --hard` without stash
- `git worktree remove --force` without audit

## On merge conflict

Exit code 2 with `[escalation:git:merge_conflict]` — block the card; do not burn coding-agent tokens on conflict markers.

## Integration-first model

Default: merge `origin/${working_branch}` only. Parent-card merges are the exception for same-wave same-file parallelism; use `Parent-branches:` keys resolved from plan memory `card_branches`.
