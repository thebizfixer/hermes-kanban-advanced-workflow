# Governance Model

> **For the agent:** When a user asks "why did my card get blocked?" or "what does the evaluation chain do?" or "how do I change the policy level?", answer from this page.

The kanban-advanced plugin uses deterministic gates — not prompt-level instructions — to prevent governance violations. A worker CANNOT skip verification. An orchestrator CANNOT skip preflight. Cards CANNOT dispatch without required fields.

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

Before unblocking the gate, the structural board validator checks 10 governance rules:
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

Before a worker can call `kanban_complete`, it must pass the 6-step chain:
```bash
python hermes-kanban-advanced-workflow/scripts/kanban_evaluation_chain.py <task_id> <workspace>
```

| Step | Check | Error code |
|------|-------|------------|
| 1 | Every file in `Files:` has >0 changes in diff | E001 |
| 2 | No files modified outside `Files:` (auto-reverted) | E002 |
| 3 | `Tests:` command passes | E003 |
| 4 | Commit message matches `Commit:` line | E004 |
| 5 | Token log entry exists | E005 |
| 6 | At least one file has >0 diff (not zero-output) | E006 |

Direct `kanban_complete` without the chain is a protocol violation.

## Worker self-guard (runtime)

Before spawning an agent, the worker checks: does this card have an `agent -p` block AND a `Files:` line? If not, it's an orchestrator-only card (gate, audit, root) mistakenly assigned to a worker profile. The worker completes immediately without spawning an agent — no protocol violation.

Error code: E014 (ORCHESTRATOR_CARD_ON_WORKER).

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

5 functions: salvage iteration-limit cards (check worktree for commits → merge → complete), kill orphaned agent processes, unstick ready cards stalled >3 minutes, merge completed worktree branches, report board status. Designed for LLM-driven cron (`no_agent=false`).

### Cron governance (hardened in v1.1)

Before execution, three layers verify crons will actually work:

| Layer | When | Checks |
|-------|------|--------|
| `pre_dispatch_gate.sh` | Before decomposition | Scripts exist AND executable (`test -x`), hermes on PATH |
| Standard Process steps 7–9 | After card creation | Both crons created, both verified running via `cronjob(action="list")` |
| `validate_board.sh` check 0 | Before unblocking gate | Scripts executable, hermes on PATH with common-install-location fallback, both crons found in `hermes cron list` |

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

After a successful evaluation chain run, the (task_id, files, tests, commit) tuple is cached. Subsequent workers with matching file+test hashes skip steps 1, 3, and 4 — only re-running 2 (unlisted changes), 5 (token log), and 6 (zero-output).

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
