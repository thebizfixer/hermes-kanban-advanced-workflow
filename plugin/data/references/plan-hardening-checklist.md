# Plan hardening checklist (first pass)

Runs between **sanity check** and **optimize for kanban**. Tier detail: `plan-hardening-methodology.md`.

## Critical

0. **Canonical plan location** — Kanban SSOT is `.hermes/kanban/plans/{plan_id}.plan.md`. If the plan was drafted elsewhere (IDE-native path, user-provided path, or another `plan_search_dirs` entry), copy it into `.hermes/kanban/plans/` during Harden before other edits. Verify: `test -f .hermes/kanban/plans/{plan_id}.plan.md` or `PYTHONPATH=scripts/lib python3 -c "from plan_paths import ensure_canonical_plan; print(ensure_canonical_plan('.', '{plan_id}'))"`. Continue hardening from the canonical copy only.
1. **Declared anchors present** — Non-trivial code-gen cards include `Anchor:` in the agent block. Run `python3 scripts/audit_anchors.py --plan <plan>.md --strict` (exit 0). Use `python3 scripts/lib/plan_parse.py suggest-anchors --plan <plan>.md` for rg-backed pin suggestions; paste results into agent blocks — do not infer file↔line pairing from prose.
2. **Declared anchors fresh** — `python3 scripts/verify_anchors.py --plan <plan>.md` passes against current `HEAD` (0 failures). Prose-only `L123` mentions in signal maps are sanity-check scope, not auto-verified.
3. Every cited file path exists on `${working_branch}`.
4. Every cited symbol (function/class) exists or is marked **new**.
5. Edge cases listed for each workstream (failure, rollback).
6. No auto-research claims without code citation.
7. `verify_goal_cards.py --plan` passes (if goal cards present).

## Important

8. Test command per workstream is runnable from repo root.
9. Deferred decisions < 30% of sections.
10. No duplicate `Files:` overlap across parallel cards (draft decomposition).
11. Iteration estimate per card ≤ 35 turns (`iteration-budget-estimation.md`).
12. Frontend plans: `Surface-slots:` or overlay `ui_stack` documented; layout/motion verbs paired with `Acceptance (layout|presentation|a11y):` bullets (`frontend-neutrality.md`).
13. `Files:` lines in agent blocks use **plain repo-relative paths** (no markdown `` [`path`](url) `` links).

## Nice-to-have

14. Consolidate same-file micro-cards.
15. **Redundant change detection** — grep plan for duplicate edits to the same function from multiple workstreams; merge.

## Report template

```markdown
## Hardening pass
- Critical: N fixed / M open
- Important: ...
- Deferred to optimize: ...
```
