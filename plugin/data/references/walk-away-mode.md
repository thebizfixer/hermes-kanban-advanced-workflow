# Walk-away mode

**Overlay key:** `walk_away_mode` in `.hermes/kanban-overrides/kanban-config.yaml`  
**Dashboard:** Kanban-Advanced → **Cron → Walk-away mode** (default **off**)  
**Legacy:** `notify_on_complete` in YAML; `NOTIFY_ON_COMPLETE` / `WALK_AWAY_MODE` env when the YAML key is absent

## What it does

When **off** (default), the orchestrator follows the interactive post-execution contract: after final audit passes, it stops at reconciliation, cleanup, and postmortem checkpoints and waits for explicit operator approval (`plugin/data/references/interaction-model.md`).

When **on**, the operator can decompose a plan and leave the keyboard. During execution:

- Wave crons (`auto_unblock`, `board_keeper`) and optional lifecycle notify continue as today.
- Intervention paging (`kanban-advanced:kanban-notify`) still fires only for true manual interventions — not routine blocks or per-card progress.

After the **final audit card** completes, `board_keeper.sh` invokes `scripts/kanban_walk_away_post_exec.sh`, which runs **without operator prompts**:

1. Token report (`kanban_token_report.py`) — reconciliation artifact  
2. Postmortem (`generate_postmortem.py`) — while task history is intact  
3. Wave cron removal (`provision_kanban_crons.sh --remove`)  
4. Board archive (all tasks)  
5. Git-safe cleanup (`git_safe_cleanup.sh`, best-effort)  
6. Completion gateway summary (`kanban_completion_notify.sh`) — same resolved `--deliver` as lifecycle (not `local`)

Idempotent per plan: `.hermes/kanban/logs/post_exec_complete_<plan_id>`.

## When to enable

- You want end-to-end unattended runs with a single **plan complete** ping when postmortem is ready.
- Gateway delivery is tested (`kanban-advanced:kanban-notify` § Gateway delivery setup).
- Governance profile and monitoring crons are appropriate for your risk tolerance (`strict` recommended for production walk-away).

## When to leave off

- You want to review reconciliation KPIs before archive.
- You stage non-kanban git changes manually after each plan.
- You prefer orchestrator-led checkpoints in chat.

## Operator flow (enabled)

1. Bootstrap / Save with **Walk-away mode** on (or set `walk_away_mode: true` in overlay).
2. Optimize plan → say **execute** / **proceed** (same gate as interactive runs).
3. Walk away — board keeper + intervention rules handle in-flight failures.
4. On success: receive `✅ Kanban plan complete — {plan_id}` with postmortem path.
5. On catastrophic / non-retryable failure: receive intervention page (🚨), not completion notify.

## Cross-references

- Post-execution script: `scripts/kanban_walk_away_post_exec.sh`
- Completion message: `scripts/kanban_completion_notify.sh`
- Orchestrator checklist: `kanban-advanced:kanban-orchestrator` § Walk-away mode
- Cleanup ordering: `kanban-advanced:kanban-cleanup`
- Interactive checkpoints: `plugin/data/references/interaction-model.md`
