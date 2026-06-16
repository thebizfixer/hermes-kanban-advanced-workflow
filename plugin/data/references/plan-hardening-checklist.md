# Plan hardening checklist (first pass)

Runs between **sanity check** and **optimize for kanban**. Tier detail: `plan-hardening-methodology.md`.

## Critical

1. Every cited file path exists on `${working_branch}`.
2. Every cited symbol (function/class) exists or is marked **new**.
3. Edge cases listed for each workstream (failure, rollback).
4. No auto-research claims without code citation.
5. `verify_goal_cards.py --plan` passes (if goal cards present).

## Important

6. Test command per workstream is runnable from repo root.
7. Deferred decisions < 30% of sections.
8. No duplicate `Files:` overlap across parallel cards (draft decomposition).
9. Iteration estimate per card ≤ 35 turns (`iteration-budget-estimation.md`).

## Nice-to-have

10. Consolidate same-file micro-cards.
11. **Redundant change detection** — grep plan for duplicate edits to the same function from multiple workstreams; merge.

## Report template

```markdown
## Hardening pass
- Critical: N fixed / M open
- Important: ...
- Deferred to optimize: ...
```
