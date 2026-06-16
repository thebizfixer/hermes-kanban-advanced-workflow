# How to: governance gates

Deterministic gates — not prompt instructions — block unsafe dispatch. Two complementary frameworks inform the design:

- **[Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)** (AGT, MIT) — "Actions the kernel denies are structurally impossible." Policy profiles (advisory/balanced/strict) govern enforcement.
- **[AEP — Agent Element Protocol](https://github.com/thePM001/AEP-agent-element-protocol)** (AEP, Apache-2.0) — Deterministic Adjudication Lattice (DAL).

**Full stack (canonical):** [`wiki/governance.md`](../../wiki/governance.md) § Full pre-execution governance stack. Summary diagram: [`docs/reference/architecture.md`](../reference/architecture.md) § Governance layers.

## Gates

| Gate                 | What it prevents                                           | How                                                                                              |
| -------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Attestation**      | Orchestrator decomposing without preflight                 | `attestation.yaml` with 120 min TTL (session-scoped). Decomposer refuses without it (A001/A002). |
| **Card body policy** | Cards lacking `Files:`, `agent -p`, or `Mode:` dispatching | `kanban_card_policy.py` validates every card. Blocked on P001/P002/P003.                         |
| **Evaluation chain** | Worker calling `kanban_complete` without verifying         | 9-step DAL. Direct `kanban_complete` is a protocol violation.                                    |
| **Error registry**   | Ad-hoc failure handling                                    | 37 canonical error codes with severity, recovery action, and retry flag.                         |
| **Lattice memory**   | Re-running cold-path checks on known-good states           | Attractor hash matching skips steps 1, 3, 4 on repeated configurations.                          |

## Running the gates

1. **Attestation** — `kanban_attestation.py <plan_id>` after preflight (A001–A003).
2. **Card body policy** — `kanban_card_policy.py --all` (P001–P004).
3. **Board validation** — `validate_board.sh` before orchestrator completes gate.
4. **Pre-dispatch** — `pre_dispatch_gate.sh` (plan on `${working_branch}`, preflight, coding-agent CLI, attestation, plan memory, DB, cron scripts, hermes PATH; OAuth pre-warm WARN after pass).
5. **Worker verification** — inline checks in worker Step 6 (see `kanban-advanced:kanban-worker` skill).

## Policy profiles (single governance knob)

One profile controls card body policy, the evaluation chain, and structural/plan validation gates.

| Profile | Card body policy | Evaluation chain | Board / plan gates |
| ------- | ---------------- | ---------------- | ------------------ |
| `advisory` | Warn, allow dispatch | Warn, allow complete | Failures → warnings |
| `balanced` (default) | Block (P001–P009) | Block task | Warnings pass with review |
| `strict` | Block + log intervention | Block + log intervention | Warnings → block |

**Set at init** — CLI (`hermes kanban-advanced init --policy-profile strict`) or dashboard **Governance profile** dropdown. Stored as `policy_profile` in `kanban-config.yaml` and `KANBAN_POLICY_PROFILE` in `.env`.

Per-run override:

```bash
export KANBAN_POLICY_PROFILE=strict
python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py --all
bash hermes-kanban-advanced-workflow/scripts/validate_board.sh
```

Full detail: [wiki/governance.md](../../wiki/governance.md) and [wiki/configuration.md](../../wiki/configuration.md).
