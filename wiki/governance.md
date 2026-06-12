# Governance Model

> **For the agent:** When a user asks "why did my card get blocked?" or "what does the evaluation chain do?" or "how do I change the policy level?", answer from this page.

The kanban-advanced plugin uses deterministic gates — not prompt-level instructions — to prevent governance violations. A worker CANNOT skip verification. An orchestrator CANNOT skip preflight. Cards CANNOT dispatch without required fields.

## Decomposition workflow (why block-on-create)

Before the four governance gates run at dispatch time, cards must be created safely on the vanilla Hermes board. See **[[decomposition-workflow]]** for the full justification agents should use when answering:

- Why cards are **blocked immediately after create** (dispatcher claims `ready` in <1s; parent links cannot retroactively stop a claimed card)
- Why **`kanban.auto_decompose=false`** (v0.15.0 default would LLM-rewrite optimized plan bodies)
- Why the **gate card is orchestrator-only** (complete after `validate_board.sh`, not a human approval step)
- Why we avoid `--triage`, `--parents`, and `--initial-status blocked` on dependent cards

Structural summary: create → block → link → crons → validate → orchestrator completes gate → `auto_unblock.sh` releases waves as parents reach `done`.

## The four gates

### 1. Attestation (orchestrator-side)

Before creating any cards, the orchestrator generates `attestation.yaml`:
```bash
python hermes-kanban-advanced-workflow/scripts/kanban_attestation.py <plan_id>
```

The attestation records: preflight status, profile validity, agent-prompt block count. Session-scoped (120 min TTL). Without a valid attestation, the decomposer refuses to create cards.

Error codes: A001 (missing), A002 (stale), A003 (tampered).

### 2. Card body policy (orchestrator-side)

After creating cards but before dispatch, every card body is validated:
```bash
python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py --all --profile balanced
```

Cards must have:
- `Files:` line — every file the agent touches
- `agent -p` fenced block — the exact command the worker executes
- `Mode:` line — `modify-only`, `create-only`, or `any`

Cards with >3 files require human approval.

Error codes: P001 (missing Files:), P002 (missing agent block), P003 (missing Mode:), P004 (too many files).

### 3. Board validation (orchestrator-side, pre-dispatch)

Before the orchestrator completes the gate card, the structural board validator checks 10 governance rules:
```bash
bash hermes-kanban-advanced-workflow/scripts/validate_board.sh
```

| Check | What it catches | Error |
|-------|----------------|-------|
| 1 | Orphaned --parents declarations | P008 |
| 2 | Code-gen cards with scratch workspace | P006 |
| 3 | Shared workspace paths | P007 |
| 4 | Missing parent links | — |
| 5 | Cards running before parents done | — |
| 6 | Function-count heuristic (>10 fns) | P009 |
| 7 | Max-retries ≤2 | — |
| 8 | Orphaned agent processes | — |
| 9 | Worker cards without agent -p blocks | P002 |
| 10 | Orchestrator-only cards on worker profiles | — |

### 4. Evaluation chain (worker-side)

Before a worker can call `kanban_complete`, it must pass the evaluation chain:
```bash
python hermes-kanban-advanced-workflow/scripts/kanban_evaluation_chain.py <task_id> <workspace>
```

**Cold path (coding cards):**

| Step | Check | Error code |
|------|-------|------------|
| 1 | Every `Files:` path has >0 diff (or prior commit with matching message + diff-tree) | E001 |
| 2 | No unlisted file changes (auto-reverted) | E002 |
| 3 | `Tests:` command passes | E003 |
| 4 | Commit message matches `Commit:` line (skipped for N/A / verification) | E004 |
| 5 | Exact token log entry (`source=agent`, matching task_id) | E018 |
| 6 | At least one file has >0 diff (or `already_committed`) | E006 |
| 7 | Net line churn within budget | E017 |
| 8 | Agent output JSON captured | E020 |
| 9 | No destructive git ops in reflog (governance artifact resets skipped) | E019 |

**Verification path (`Type: verification`):** runs steps 3 + 9 only — no coding-agent dispatch, no diff/token checks.

**Policy carve-outs:** `Type: orchestrator-handoff` and `Type: verification` exempt from P001–P003.

Direct `kanban_complete` without the chain is a protocol violation.

## Worker self-guard (runtime)

**E014 — orchestrator-only:** If the card has **neither** an `agent -p` block **nor** a `Files:` line, complete without spawning an agent (gate, audit, root).

**Verification-only (`Type: verification`):** Takes precedence over any `agent -p` block at runtime — run `Tests:` via `terminal()` only, no `coding_agent_invoke.sh`, then the evaluation chain before `kanban_complete`. At decomposition, `validate_board.sh` rejects verification cards that still carry `Files:` or `agent` blocks (use `Type: verification` + `Tests:` only).

Error code: E014 (ORCHESTRATOR_CARD_ON_WORKER / verification contradictions on malformed cards).

## Auto-progression (mechanical wave unblocking)

LLM orchestrators cannot poll the board autonomously. Wave progression (checking parent completion → unblocking children) is delegated to a script:
```bash
bash hermes-kanban-advanced-workflow/scripts/auto_unblock.sh
```
Run via cron every 60s during execution. Handles every wave transition without orchestrator intervention.

### Board keeper (proactive salvage)

A second cron runs every 180s for proactive board management:
```bash
bash hermes-kanban-advanced-workflow/scripts/board_keeper.sh
```

5 functions: salvage iteration-limit cards (check worktree for commits → merge → complete), kill orphaned agent processes, unstick ready cards stalled >3 minutes, merge completed worktree branches, report board status. Runs as **script-only** Hermes cron (`no_agent=true`, `deliver=local`).

### Cron governance (hardened in v1.1)

**Lifecycle:** Init/bootstrap materializes **script files** only. **Cron jobs** are created per plan at decomposition (`provision_kanban_crons.sh --create`) and removed at cleanup (`--remove`). Gateway must run for ticks; messaging platforms are optional.

| Layer | When | Checks |
|-------|------|--------|
| `pre_dispatch_gate.sh` | Before decomposition | Script files executable, hermes on PATH; warns if gateway down |
| Decomposition Steps 3–5 | Before impl cards | `provision_kanban_crons.sh --create` + `--check` |
| `validate_board.sh` check 0 | Before completing gate | `provision_kanban_crons.sh --check` (active, deliver=local, no-agent) |

**Why hermes PATH matters:** Cron jobs run in a minimal environment. If `hermes` is at `~/.local/bin/hermes` but cron's PATH doesn't include `~/.local/bin`, `auto_unblock.sh` and `board_keeper.sh` will fail silently. The gate checks for this before any cards are dispatched.

**Why executable matters:** `provision.sh` does `chmod 755`, but a stale copy or manual edit can strip the executable bit. A non-executable cron script fails silently on every tick — no error, no notification, no wave progression. The gate catches this.

## Pre-dispatch gate (single entry point)

The `pre_dispatch_gate.sh` script replaces the old multi-step Steps 0a–0e:
```bash
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

Runs in order: plan on `${working_branch}` → plan pushed → preflight → attestation → card policy present → plan memory seeded → DB integrity → cron scripts executable → hermes on PATH. Fails on any blocking check.

## Governance integrity (pre-decomposition)

Before any board is decomposed, verify the entire governance layer is intact:
```bash
bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh
```

Checks all four tiers: skills (8 files via provision.sh --check), scripts (17 files exist + executable), registry (error-codes.yaml), policies + prompts (3 files). 30 checks total. Exit 1 if any file is missing or non-executable.

## Lattice memory

After a successful evaluation chain run, the (task_id, files, tests) tuple is cached. Attractor fast-path re-runs steps 2, E018, E020, 6, E017, E019 — skipping 1, 3, 4. Verification cards use a separate short path.

## Recovery

When any gate fails:
```bash
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py <task_id> <error_code>
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --cascade   # multi-failure triage
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --list      # all recovery actions
```

Recovery order for cascades: environment → agent → governance infra → verify.

## Changing policy level

**Persistent (recommended):** set at init or in the dashboard **Governance profile** dropdown. Writes `policy_profile` to `kanban-config.yaml` and `KANBAN_POLICY_PROFILE` to the project `.env`.

```bash
hermes kanban-advanced init --policy-profile strict
# or edit kanban-config.yaml: policy_profile: "strict"
```

**Per-run override:**

```bash
KANBAN_POLICY_PROFILE=strict python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py --all
bash hermes-kanban-advanced-workflow/scripts/validate_board.sh --profile strict
```

The same profile applies to card body policy, the evaluation chain, and board/plan validation gates.

## Design sources

This model adopts patterns from:
- [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit) (MIT) — `govern()` decorator, attestation gate, policy profiles
- [AEP — Agent Element Protocol](https://github.com/thePM001/AEP-agent-element-protocol) (Apache-2.0) — Deterministic Adjudication Lattice, error registry, lattice memory
