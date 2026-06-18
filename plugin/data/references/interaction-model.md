# Interaction Model — Post-Execution Checkpoints

After the last implementation card completes, the orchestrator MUST stop at each checkpoint and ask the user before proceeding — **unless** `walk_away_mode: true` in overlay (dashboard **Cron → Walk-away mode**). When walk-away mode is on, `board_keeper.sh` invokes `kanban_walk_away_post_exec.sh` after final audit without operator prompts. See `plugin/data/references/walk-away-mode.md`.

## Checkpoint sequence (mandatory)

| # | Checkpoint | Trigger | What happens | User response |
|---|-----------|---------|--------------|---------------|
| 1 | **Final audit** | Last card done → audit card auto-promotes | Full verification suite: file compliance, lint/typecheck, tests, post-merge gate, cross-card regression, churn audit, KPI integrity | "Proceed" or specific fixes |
| 2 | **Reconciliation** | Audit passes | Compliance check, token burn report, failure-mode taxonomy, non-kanban overhead tally, skill updates, publishable sync | "Yes" to proceed, or specific items to address |
| 3 | **Postmortem** | Reconciliation done | Run `generate_postmortem.py` **before** archive (metrics from `kanban.db` + token JSONL; `archived` status counts as terminal). Cross-check KPI `total_tasks` vs plan memory `task_ids`. Confirm all 8 sections. | "Yes" to proceed |
| 4 | **Cleanup** | Postmortem written | Remove wave crons, kill tmux watch, archive tasks, remove stale git locks, `git_safe_cleanup.sh --audit` then `--clean` | Board complete |

**Walk-away parity:** `kanban_walk_away_post_exec.sh` runs steps 2–4 in the same order (token report → postmortem → archive/crons → git cleanup) without prompts.

## What the orchestrator MUST say at each checkpoint

### Checkpoint 1 — Final audit complete

```
Final audit complete.
- N/N files compliant, M/M tests pass, cross-card regression clean.
- Token log: present/missing. Intervention counter: N.

Proceed to reconciliation? Say "yes" or tell me what to fix.
```

### Checkpoint 2 — Reconciliation complete

```
Reconciliation complete.
- Token burn: ~XXX tokens (orchestrator + worker + CLI agent)
- Success rate: N%, autonomous: N%, interventions: N
- Dominant failure: <mode> (N%)
- Skill updates needed: <list or "none">

Proceed to postmortem? Say "yes" or tell me what to address.
```

### Checkpoint 3 — Postmortem complete

```
Postmortem written: .hermes/kanban/reports/<plan_id>_postmortem_YYYY-MM-DD.md
- 8 sections: execution summary, agent performance, failure taxonomy,
  intervention log, discovered pitfalls, skill updates, token economics,
  learning summary.
- KPI JSON: .hermes/kanban/reports/<plan_id>_kpi.json

Proceed to cleanup? Say "yes" and I'll archive the board and remove crons.
```

### Checkpoint 4 — Cleanup complete

```
Cleanup complete.
- Wave crons removed, board archived, worktrees cleaned.

Board complete. Review the postmortem before the next plan.
```

## Timing

When `walk_away_mode: false` (default), the orchestrator should present each checkpoint within 1-2 turns of the previous step completing. If the user doesn't respond, wait — do not auto-advance. If >30 minutes pass with no response, surface a summary of what's waiting.

When `walk_away_mode: true`, `board_keeper.sh` runs `kanban_walk_away_post_exec.sh` after final audit — checkpoints 2–4 are automated in postmortem-before-archive order; do not wait for operator yes.

## Anti-patterns

- **Silently finishing (walk_away_mode off).** The orchestrator completes the final audit and says nothing. The user has to check the board manually.
- **Skipping checkpoints without walk-away mode.** "All done — reconciliation, cleanup, and postmortem complete." All three in one message with no user gate when `walk_away_mode: false`.
- **Archive before postmortem.** `hermes kanban list` hides archived cards; postmortem still works from `kanban.db`, but agents waste turns redirecting. Match walk-away: postmortem first.
- **Assuming consent.** "I'll proceed to reconciliation now." The user didn't say yes.
- **Missing data.** Token log or intervention counter missing → flag it, don't skip the section. Estimate from logs if data sources are absent.
