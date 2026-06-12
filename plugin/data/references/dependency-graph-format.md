# Dependency graph format (decomposition)

ASCII dependency graph for orchestrator link planning before `hermes kanban link`.

## Template

```text
Plan: <plan_id>
Wave 0 (gate): [GATE-<plan_id>]
Wave 1 (parallel):
  [CARD-A] ──┐
  [CARD-B] ──┼──> [CARD-D]
  [CARD-C] ──┘
Wave 2:
  [CARD-D] --> [AUDIT-<plan_id>]
```

## Rules

- **Gate card** blocks all implementation children until orchestrator completes it after `validate_board.sh`.
- **Parent done** before child `ready` — use block-on-create + `auto_unblock.sh`, not `--triage`.
- Label nodes with **card title slug** or task id prefix from decomposition draft.
- Mark **goal-mode** cards with `(goal)` — max **2** per plan (`goal_card_budget`).

## Verify before create

- No orphan implementation cards without a parent path to GATE or root audit.
- Parallel lanes in the same wave must not edit the same `Files:` paths (P004 / split discipline).
