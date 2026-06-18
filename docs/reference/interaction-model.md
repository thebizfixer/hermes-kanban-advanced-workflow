# Interaction Model

The workflow moves through distinct stages. Each stage has a trigger phrase — say it and the agent advances. Between stages, the agent waits for you unless **Walk-away mode** is enabled (dashboard **Cron** toggle or `walk_away_mode: true` in overlay).

## Planning stage (interactive)

| You say                                  | Agent does                                                                                                                                                                                  | Next                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `"Plan this out"` or link to a plan file | Drafts a plan from your goal (IDE-native path OK; canonical location is `.hermes/kanban/plans/` after Harden)                                                                                                                                  | Waits for your review                                                     |
| `"Do a sanity check"` / `"sanity check the plan"` | Read-only audit of anchor points, code claims, and gaps. Flags when the plan is not yet in `.hermes/kanban/plans/` (copy happens in Harden, not during sanity). | Findings list — proceed to Harden |
| `"Harden the plan"`                      | Sanity check first, then tier-gated hardening pass (Critical → Important → Nice-to-have). Copies the plan to `.hermes/kanban/plans/` if needed, then closes gaps in WHAT the plan is for: anchor points, edge cases, redundant changes, auto-research. | Prompts for review                                                        |
| At any point: `"Revise section X"`       | Edits the plan in-place                                                                                                                                                                     | Returns to review                                                         |
| `"Optimize for Kanban"`                  | Closes gaps in HOW the plan executes on Kanban: adds `agent -p` blocks, draws dependency graph, estimates iteration budgets, plans same-provider staggering, adds Files:/Mode: lines.       | Prompts: *"Plan optimized. Ready when you are — say proceed or execute."* |

Iterate on harden → revise as many times as needed. Optimize is the final gate — once you say it, the plan is locked for decomposition. You can still revise after optimizing, but you'll need to re-optimize to regenerate agent-prompt blocks and line budget.

**Walk-away point:** After the plan is written but before you say "execute." After Harden, the canonical copy sits in `.hermes/kanban/plans/` — come back hours or days later and say "execute this plan."

## Execution stage

| You say                                     | Agent does                                                                                          | Next                                                                    |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `"Execute the plan"` / `"Proceed"` / `"Go"` | Runs preflight → attestation → card body policy → decomposes into kanban cards → dispatches workers | Wave crons + board keeper monitor the board                             |

During execution, workers supervise coding agents and the evaluation chain gates every completion. Intervention-only gateway pages fire for true manual failures (`kanban-advanced:kanban-notify`). Optional per-card lifecycle messages use **Lifecycle notify** (separate dashboard toggle).

## Post-execution

Controlled by **Walk-away mode** (`walk_away_mode`, default **off**). Full contract: `plugin/data/references/walk-away-mode.md`.

### Walk-away mode off (default — checkpointed)

After final audit passes, the agent prompts at each stage:

| Agent prompts                                                          | You say                | Agent does                                                                      |
| ---------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| *"Final audit complete. Proceed to reconciliation?"*                   | `"Yes"` / `"Proceed"`  | File-level compliance, token burn report, failure-mode taxonomy                 |
| *"Reconciliation complete. Proceed to postmortem?"*                    | `"Yes"` / `"Proceed"`  | Generates postmortem + KPI JSON from `kanban.db` (before archive)               |
| *"Postmortem complete. Proceed to cleanup?"*                             | `"Yes"` / `"Clean up"` | Archives board, removes wave crons, cleans worktrees                            |

You can say `"No"` or `"Wait"` at any checkpoint — the agent holds state and resumes when you're ready.

### Walk-away mode on (dashboard **Cron → Walk-away mode**)

1. Enable the toggle (or set `walk_away_mode: true`) before decomposition.
2. Say `"Execute the plan"` — same preflight and gate as interactive runs.
3. Leave the keyboard. Board keeper handles in-flight recovery; intervention pages only for non-retryable failures.
4. After final audit, `kanban_walk_away_post_exec.sh` runs reconciliation artifact → postmortem → archive → cleanup → one **plan complete** gateway message with the postmortem path.

No post-execution prompts required.
