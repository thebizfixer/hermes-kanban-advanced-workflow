# Interaction Model

The workflow moves through distinct stages. Each stage has a trigger phrase — say it and the agent advances. Between stages, the agent waits for you.

## Planning stage (interactive)

| You say                                  | Agent does                                                                                                                                                                                  | Next                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `"Plan this out"` or link to a plan file | Drafts a plan from your goal, writes it to `.agent/plans/`                                                                                                                                  | Waits for your review                                                     |
| `"Harden the plan"`                      | Sanity check first, then tier-gated hardening pass (Critical → Important → Nice-to-have). Closes gaps in WHAT the plan is for: anchor points, edge cases, redundant changes, auto-research. | Prompts for review                                                        |
| At any point: `"Revise section X"`       | Edits the plan in-place                                                                                                                                                                     | Returns to review                                                         |
| `"Optimize for Kanban"`                  | Closes gaps in HOW the plan executes on Kanban: adds `agent -p` blocks, draws dependency graph, estimates iteration budgets, plans same-provider staggering, adds Files:/Mode: lines.       | Prompts: *"Plan optimized. Ready when you are — say proceed or execute."* |

Iterate on harden → revise as many times as needed. Optimize is the final gate — once you say it, the plan is locked for decomposition. You can still revise after optimizing, but you'll need to re-optimize to regenerate agent-prompt blocks and line budget.

**Walk-away point:** After the plan is written but before you say "execute." The plan sits in `.agent/plans/` — come back hours or days later and say "execute this plan."

## Execution stage (walk-away)

| You say                                     | Agent does                                                                                          | Next                                                                    |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `"Execute the plan"` / `"Proceed"` / `"Go"` | Runs preflight → attestation → card body policy → decomposes into kanban cards → dispatches workers | Cron monitor takes over                                                 |
| At any point: `"Execute in walk-away mode"` | Same as above + explicit confirmation that notifications will be intervention-only                  | You walk away; intervention-only notifications plus one completion ping |

During execution, workers supervise coding agents and the evaluation chain gates every completion. You don't need to be present. The cron monitor watches and alerts you only if intervention is required.

## Post-execution (checkpointed)

After all cards complete, the agent prompts you at each stage:

| Agent prompts                                                          | You say                | Agent does                                                                      |
| ---------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| *"Kanban complete. Proceed to reconciliation?"*                        | `"Yes"` / `"Proceed"`  | Runs file-level compliance, token burn report, failure-mode taxonomy            |
| *"Reconciliation complete. Ready to clean up?"*             | `"Yes"` / `"Clean up"` | Archives board, removes wave crons (`provision_kanban_crons.sh --remove`) + optional monitor, cleans worktree branches |
| *"Cleanup complete. Ready for post-mortem report?"*        | `"Yes"` / `"Proceed"`  | Generates postmortem with timeline, KPIs, failure taxonomy, and lessons learned |

You can say `"No"` or `"Wait"` at any checkpoint — the agent holds state and resumes when you're ready. You can also skip stages: `"Skip reconciliation, go to postmortem."`
