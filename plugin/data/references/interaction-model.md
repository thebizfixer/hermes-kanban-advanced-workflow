# Interaction Model — Post-Execution Checkpoints

After the last implementation card completes, the orchestrator MUST stop at each checkpoint and ask the user before proceeding. Never auto-advance.

## Checkpoint sequence (mandatory)

| # | Checkpoint | Trigger | What happens | User response |
|---|-----------|---------|--------------|---------------|
| 1 | **Final audit** | Last card done → audit card auto-promotes | Full verification suite: file compliance, lint/typecheck, tests, post-merge gate, cross-card regression, churn audit, KPI integrity | "Proceed" or specific fixes |
| 2 | **Reconciliation** | Audit passes | Compliance check, token burn report, failure-mode taxonomy, non-kanban overhead tally, skill updates, publishable sync | "Yes" to proceed, or specific items to address |
| 3 | **Cleanup** | Reconciliation done | Remove monitoring crons, kill tmux watch, archive tasks, remove stale git locks, `git_safe_cleanup.sh --audit` then `--clean` | "Yes" to proceed |
| 4 | **Postmortem** | Cleanup done | Generate `generate_postmortem.py`, confirm all 8 sections present, flag missing data sources, append operator notes | "Yes" to proceed, board complete |

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

Proceed to cleanup? Say "yes" or tell me what to address.
```

### Checkpoint 3 — Cleanup complete

```
Cleanup complete.
- Monitoring crons removed, board archived, worktrees cleaned.

Proceed to postmortem? Say "yes" and I'll generate it.
```

### Checkpoint 4 — Postmortem complete

```
Postmortem written: .hermes/kanban/reports/<plan_id>_postmortem_YYYY-MM-DD.md
- 8 sections: execution summary, agent performance, failure taxonomy,
  intervention log, discovered pitfalls, skill updates, token economics,
  learning summary.

Board complete. Review the postmortem before the next plan.
```

## Timing

The orchestrator should present each checkpoint within 1-2 turns of the previous step completing. If the user doesn't respond, wait — do not auto-advance. If >30 minutes pass with no response, surface a summary of what's waiting.

## Anti-patterns

- **Silently finishing.** The orchestrator completes the final audit and says nothing. The user has to check the board manually.
- **Skipping checkpoints.** "All done — reconciliation, cleanup, and postmortem complete." All three in one message with no user gate.
- **Assuming consent.** "I'll proceed to reconciliation now." The user didn't say yes.
- **Missing data.** Token log or intervention counter missing → flag it, don't skip the section. Estimate from logs if data sources are absent.
