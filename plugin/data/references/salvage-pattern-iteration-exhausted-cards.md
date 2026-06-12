# Salvage pattern — iteration-exhausted cards

When a card blocked after max retries but partial work exists in the worktree:

## E001 false positive (salvaged worktree)

`find_prior_commit` defaults to `HEAD~1`. After rebase or salvage, the matching commit may be deeper.

```bash
python3 scripts/kanban_evaluation_chain.py \
  --task-id <id> \
  --workspace <worktree> \
  --baseline HEAD~20
```

**Verify:** Chain finds prior commit or returns clear DENY — then re-dispatch agent or complete with evidence.

## Orchestrator salvage (MBB)

1. `hermes kanban show <task_id>` — read block reason and diagnostics.
2. `python3 scripts/kanban_recover.py --list` — retryable codes only.
3. If work is present but chain DENYs on baseline: widen baseline or create verification card.
4. Do not `kanban_complete` without evaluation chain pass.

See `kanban-orchestrator-governance` § Salvage and `wiki/troubleshooting.md` § salvage.
