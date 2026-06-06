# How to: governance gates

Deterministic gates — not prompt instructions — block unsafe dispatch. Two complementary frameworks inform the design:

- **[Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)** (AGT, MIT) — "Actions the kernel denies are structurally impossible." Policy profiles (advisory/balanced/strict) govern enforcement.
- **[AEP — Agent Element Protocol](https://github.com/thePM001/AEP-agent-element-protocol)** (AEP, Apache-2.0) — Deterministic Adjudication Lattice (DAL).

## Gates

| Gate                 | What it prevents                                           | How                                                                                              |
| -------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Attestation**      | Orchestrator decomposing without preflight                 | `attestation.yaml` with 120 min TTL (session-scoped). Decomposer refuses without it (A001/A002). |
| **Card body policy** | Cards lacking `Files:`, `agent -p`, or `Mode:` dispatching | `kanban_card_policy.py` validates every card. Blocked on P001/P002/P003.                         |
| **Evaluation chain** | Worker calling `kanban_complete` without verifying         | 6-step DAL. Direct `kanban_complete` is a protocol violation.                                    |
| **Error registry**   | Ad-hoc failure handling                                    | 23 canonical error codes with severity, recovery action, and retry flag.                         |
| **Lattice memory**   | Re-running cold-path checks on known-good states           | Attractor hash matching skips steps 1, 3, 4 on repeated configurations.                          |

## Running the gates

1. **Attestation** — `kanban_attestation.py <plan_id>` after preflight (A001–A003).
2. **Card body policy** — `kanban_card_policy.py --all` (P001–P004).
3. **Board validation** — `validate_board.sh` before unblocking gate.
4. **Pre-dispatch** — `pre_dispatch_gate.sh` (plan on `${working_branch}`, preflight, memory, DB).
5. **Worker verification** — inline checks in worker Step 6 (see `kanban-advanced:kanban-worker` skill).

## Policy Profiles

| Profile              | Missing `Files:`        | Missing `agent -p`      | Evaluation chain fail   |
| -------------------- | ----------------------- | ----------------------- | ----------------------- |
| `advisory`           | Warn, continue          | Warn, continue          | Warn, complete anyway   |
| `balanced` (default) | Block card (P001)       | Block card (P002)       | Block task              |
| `strict`             | Block + notify operator | Block + notify operator | Block + notify operator |

Set via `KANBAN_POLICY_PROFILE` env var:

```bash
export KANBAN_POLICY_PROFILE=strict
python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py --all --profile strict
```

Full detail: [wiki/governance.md](../../wiki/governance.md).
