# Execution doctrine — 80% deterministic, 20% agent-driven

> **SSOT** for what the plugin enforces vs what the operator and agents own. Cross-link: `wiki/governance.md` § Execution doctrine.

## Authority chain

1. **Operator** authors the plan (what).
2. **Plan** defines rails: `Files:`, `Acceptance:`, `Tests:`, waves, verify/deploy criteria.
3. **Deterministic layer (~80%)** enforces logistics: shell-valid `Tests:`, path normalization, scope ⊆ plan, eval-chain steps, idempotent gates.
4. **Agent layer (~20%)** implements code inside `Files:`, chooses decomposition granularity within plan todos, retry/salvage tactics.

The plugin **must not** silently rewrite plan markdown or `Acceptance:` text. It may **sanitize logistics** (strip invalid shell syntax from `Tests:`, normalize `Files:` paths) without changing product intent.

## WARN vs BLOCK phases

| Phase | When | Profile behavior |
| --- | --- | --- |
| **WARN** | `kanban_decompose --dry-run`, advisory preflight | Log violations; show sanitized `Tests:` diff; no board writes |
| **BLOCK** | `pre_dispatch_gate`, `validate_board.sh`, `kanban_card_policy.py` | `balanced` / `strict` block dispatch until operator fixes plan or card body |

Guardrails concentrate **before dispatch** so the operator can edit the plan during Draft / Harden / Optimize without fighting automation.

## Idempotency

Same plan + same board state → same gate outcomes on re-run:

| Operation | Contract |
| --- | --- |
| `sanitize_tests_command` | Strip trailing parenthetical; preserve command intent |
| `pre_dispatch_gate.sh` | Re-runnable; same pass/fail on unchanged inputs |
| `provision_kanban_crons.sh --create` | Reuse existing job IDs; no duplicate crons |
| `kanban_decompose` | Exit 7 if duplicate keys remain; orchestrator archives non-running plan cards before re-decompose |

## Escape hatches (operator intent)

If a gate would block something the operator **intentionally** wants (e.g. deliberate test-first split):

- Edit the plan: `TDD: allowed`, explicit two-card split, or adjusted `Tests:` / `Acceptance:`.
- Supervised runs: `policy_profile: advisory` (WARN only).

Do not rely on silent plugin overrides.

## v7 logistics fixes (deterministic)

| Fix | Validates | Does not decide |
| --- | --- | --- |
| `Tests:` sanitize + P014 | Runnable shell | Which test command to use |
| `Files:` normalize | Paths match git | Which files belong in scope |
| `validate_card_bodies` | Card bodies ⊆ plan Spec | Orchestrator card split shape |
| verify-deploy attestation | Operator deploy criteria met | When deploy is acceptable |

## References

- External citations: `wiki/external-references.md` § v7 hardening sources
- Plan format: `plugin/data/references/plan-file-format.md`
- Governance stack: `wiki/governance.md`
