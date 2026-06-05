# How to use goal-mode cards on an advanced board

Goal-mode is a **vanilla Hermes** feature (≥ 0.15.2). This bundle **enhances** it with preflight, card policy, and the evaluation chain — it does not replace upstream behavior.

## Prerequisites

- Hermes Agent **≥ 0.15.2**
- `hermes kanban create --help` lists `--goal` and `--goal-max-turns`
- Kanban-advanced plugin installed (`hermes plugins install thebizfixer/hermes-kanban-advanced-workflow`) and plan **Hardened** with scenario tags

## Configure the judge model

Goal loops use an **auxiliary judge** (separate from the worker and coding-agent models). In `~/.hermes/config.yaml`, configure the goals / auxiliary task per [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals).

Prefer a **fast, JSON-stable** model for the judge. The worker profile’s `model.default` still governs the coding-agent handoff.

## When to use `--goal` on a card

1. During **Harden**, consult the `kanban-planning` skill for goal-card selection criteria (scenarios D1–D10 vs A1–A10).
2. Set `goal_card: true` only when the decision checklist passes and `goal_card_budget` allows (default **2** per plan).
3. During **Optimize**, add an **`Acceptance:`** block per goal workstream.
4. At decomposition, orchestrator passes `--goal` and optional `--goal-max-turns` (default upstream: **20**).

**Default:** one-shot worker cards without `--goal`.

## Write acceptance criteria

Use the four-part template described in the `kanban-planning` skill:

- **Object** — what must exist
- **Done when** — observable condition
- **Verify** — command the worker runs (also reflected in `Tests:` for the eval chain)
- **Out of scope** — what must not change

The Hermes judge reads **card title + full body**. Keep `Acceptance:` at the top of the body; keep `Files:`, `Mode:`, and the `agent -p` block below for the worker and eval chain.

## Stacked verification

```text
Coding agent → worker verify → evaluation chain → kanban_complete
                    ↑                                    ↑
              (each goal turn)              (required every completion attempt)
```

If the Hermes judge says continue, the worker may run another coding-agent cycle. **Do not** call `kanban_complete` without passing the evaluation chain because the judge approved the turn.

When the turn budget is exhausted, upstream **blocks** the card for human review (not silent completion).

## CLI example

```bash
hermes kanban create "integration-ci-green" \
  --assignee "${worker_profile}" \
  --workspace "worktree:/tmp/wt-myplan-ci" \
  --goal \
  --goal-max-turns 18 \
  --body "Acceptance:
- Done when: pytest and integration suite green on working branch
- Verify: pytest tests/ -q && ./scripts/integration_smoke.sh

Files: ...
Mode: modify-only

\`\`\`agent
agent -p \"...\"
\`\`\`"
```

Substitute `${worker_profile}` from your overlay at provision time.

## `/goal` vs `--goal` on a card

| | `/goal` | `--goal` card |
| --- | --- | --- |
| Scope | Current CLI/gateway session | Single kanban task |
| Governance | Vanilla | Advanced (attestation, policy, eval chain) |
| Parallelism | One agent | Part of a decomposed board |
| Best for | Quick standing objectives | One stubborn lane on a governed board |

## Further reading

- [Kanban goal-mode (upstream)](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals)
- [Slash commands `/goal`](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)
- [why-kanban-advanced.md](../explanation/why-kanban-advanced.md)
