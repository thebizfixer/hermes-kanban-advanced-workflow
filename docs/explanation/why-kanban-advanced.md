# Why kanban-advanced?

Vanilla `hermes kanban` gives a board; this plugin adds **governance**: preflight, attestation, card-body policy, pre-dispatch gates, plan memory, and reconciliation patterns hardened from production use.

## What it adds

- **Decompose** work into cards with explicit dependencies and profiles (block-on-create pattern — see [wiki/decomposition-workflow.md](../../wiki/decomposition-workflow.md) for why vanilla `hermes kanban` needs this).
- **Gate** dispatch so workers cannot skip verification or files boundaries.
- **Recover** from known failure modes via registry + scripts.
- **Stay portable** — neutral canonical skills; project names live in overlay config only.

For DMAIC mapping see [six-sigma-mapping.md](six-sigma-mapping.md).

## When NOT to use kanban-advanced

The advanced workflow is overkill for:

**Single-file, single-change fixes.** If the task is "rename a variable" or "update one config value," the overhead of plan → optimize → preflight → attest → decompose → execute → verify → audit → reconcile → cleanup → postmortem is not worth it. Use `agent -p "rename X to Y in file Z"` directly or vanilla kanban if you want the audit trail without the governance pipeline.

**One-shot questions or research tasks.** "What does this function do?" or "Find all callers of this API" don't need a kanban board. The orchestrator can handle research directly without decomposition.

**No code generation involved.** If the plan is purely documentation, analysis, or conversation with no coding agent spawning, the worker supervision lifecycle and evaluation chain add no value. The orchestrator can execute these directly.

**Cost-sensitive or single-provider environments.** Each stage burns tokens (orchestrator planning, worker supervising, coding agent implementing, evaluation chain verifying). Without at least one dedicated provider per role (see [provider-strategy.md](../how-to/provider-strategy.md)), rate limits will serialize everything and wall-clock time will balloon.

**Small or single-contributor repos.** The workflow shines on multi-file, multi-workstream plans where parallel decomposition and merge discipline matter. A 3-file hobby project doesn't benefit from worktree isolation and parent-child dependency chains.

**When you need it done in under 2 minutes.** The governance pipeline alone (preflight + attestation + card policy) takes 30–60 seconds. Add decomposition, dispatch, and the evaluation chain, and the minimum viable execution time is measured in minutes, not seconds. For latency-sensitive fixes, use the coding agent directly.

If you're unsure, start with `/goal` on a small task. Graduate to vanilla kanban when you need parallel workstreams or crash resilience. Reach for kanban-advanced when you find yourself re-running the same agent because it missed something the first time — or when you need proof that it didn't.

## Three-tier tool choice

| Scope | Tool |
| --- | --- |
| Small / no board | Hermes `/goal` or direct `agent -p` |
| Multi-lane governed delivery | This plugin (default **one-shot** kanban cards) |
| One stubborn outcome lane | Same board + **`--goal`** on 0–2 cards after Harden (see `kanban-advanced:kanban-planning` skill § Goal-card selection) |

Requires Hermes **≥ 0.16.0** (tested on 0.16.0). Goal-mode (`--goal`) **enhances** vanilla Hermes; the evaluation chain still gates every completion.
