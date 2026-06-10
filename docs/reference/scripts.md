# Governance Scripts

Every governance script is in `scripts/`.  All paths below use `${bundle_path}/scripts/` (canonical) or `hermes-kanban-advanced-workflow/scripts/` (relative from repo root).

## Pre-dispatch gate (`pre_dispatch_gate.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

Single gate before decomposition. Runs in order: plan on `${working_branch}` → plan pushed → preflight → attestation → card policy present → plan memory seeded → DB integrity → **cron scripts executable** → **hermes on PATH**.  Replaces the old multi-step Steps 0a–0e.  Fails on any blocking check with a specific error.

Added checks in v1.1: `test -x` (not just `test -f`) for cron scripts, and hermes PATH verification so crons can invoke `hermes kanban` commands.

## Board validation (`validate_board.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/validate_board.sh [--strict] [--profile advisory|balanced|strict]
```

Pre-dispatch structural gate.  Run after card creation and cron provisioning, before the orchestrator completes the gate card. 12 checks:

| # | Check | What it catches |
|---|-------|----------------|
| 0 | **Cron health** — scripts executable, hermes on PATH, both crons running | Silent cron failures, cron environment PATH mismatch |
| 1 | Orphaned `--parents` declarations | P008 |
| 2 | Code-gen cards with scratch workspace | P006 |
| 3 | Shared workspace paths | P007 |
| 4 | Missing parent links | Dependency gaps |
| 5 | Cards running before parents done | Dispatch ordering |
| 6 | Function-count heuristic (>10 fns) | P009 |
| 7 | Max-retries ≤2 | Infinite retry loops |
| 8 | Orphaned agent processes | Resource leaks |
| 9 | Worker cards without `agent -p` blocks | P002 |
| 10 | Orchestrator-only cards on worker profiles | Protocol violation prevention |
| 11 | Worker cards without `Tests:` line | E003 prevention |

Cron health (check 0) was hardened in v1.1: per-script executable verification, both `auto_unblock` and `board_keeper` crons verified running, and hermes PATH check with common-install-location fallback.

## Preflight (`preflight.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
```

Environment gating before decomposition. 8 checks: filesystem coherence, kanban DB integrity, memory budget, secret availability, API reachability, hermes version + goal flag, gateway health, profile availability, environment parity.  Returns JSON with `status: pass | degraded | fail`.  See `kanban-advanced:kanban-preflight` skill for full details.

## Cron scripts

### `auto_unblock.sh`

```bash
bash scripts/auto_unblock.sh [--dry-run] [--json]
```

Polls the board and unblocks cards whose parents are all done.  Run via cron every 60s during execution.  Mechanical wave progression — the orchestrator doesn't need to manually unblock each wave.  Uses `HERMES_HOME` to find `kanban.db`.

### `board_keeper.sh`

```bash
bash scripts/board_keeper.sh
```

Proactive board manager for walk-away execution.  Runs every 180s.  5 functions:
1. Salvage iteration-limit cards (check worktree, commit, merge, complete)
2. Kill orphaned agent processes from archived cards
3. Unstick ready cards stalled >3 minutes
4. Detect unmerged done cards (commits ahead of `${working_branch}`)
5. Report board status

Designed for LLM-driven cron (`no_agent=false`) — the script output feeds the agent's decision loop. Calls `kanban_escalation_tracker.sh` for **every** blocked card and emits `ESCALATE:` / `HUMAN_INTERVENTION:` signals to stdout (`RETRY:` auto-unblocks silently).

### `kanban_escalation_tracker.sh`

```bash
bash scripts/kanban_escalation_tracker.sh \
  --task-id t_abc123 \
  --block-reason "[escalation:coding_agent:attempt:3] E003: tests failed" \
  --config .hermes/kanban-overrides/kanban-config.yaml
```

Per-card escalation state machine (`coding_agent` → `worker` → `orchestrator` → human). Reads `escalation_max_attempts` from config. Writes state to `.hermes/kanban/escalation/<task_id>.json`.

### `worktree_setup.sh`

```bash
bash scripts/worktree_setup.sh \
  --task-id t_abc123 \
  --repo-root .
```

Atomic worktree lifecycle: prune stale entries → create/reuse worktree → cross-platform workspace trust → install pre-push and pre-commit hooks. Reads `working_branch` and `trigger_branch` from config (no hardcoded fallbacks). Outputs `WORKTREE_PATH=<path>` on stdout.

### `install_pre_push_hook.sh` / `install_pre_commit_hook.sh`

Called by `worktree_setup.sh`. Pre-push blocks pushes to branches other than the card worktree branch (`wt/<task_id>`). Pre-commit enforces the `Files:` boundary via `.kanban-scope` written by the worker before agent spawn.

## Provisioning (`provision.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/provision.sh          # materialize
bash hermes-kanban-advanced-workflow/scripts/provision.sh --check  # verify no drift
```

Syncs canonical skill files from `plugin/skills/` to `$HERMES_HOME/skills/kanban-advanced/`.  Applies overlay patches from `.hermes/kanban-overrides/patches/`.  `--check` mode exits non-zero if materialized files have drifted from canonical.

## Decomposition (`kanban_decompose.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_decompose.py --plan <file> [--dry-run]
```

Governed card creation from a plan file.  Reads the plan, extracts workstreams, creates cards with proper `Files:`/`Mode:`/`agent -p` blocks, wires parent-child dependencies.

## Evaluation chain (`kanban_evaluation_chain.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_evaluation_chain.py <task_id> <workspace> --baseline HEAD~1
```

9-step Deterministic Adjudication Lattice (AEP DAL pattern). Each step returns ALLOW/DENY with canonical error code:

| Step | Code | What it checks |
|------|------|---------------|
| 1 | E001 | Every file in `Files:` has >0 changes |
| 2 | E002 | **Hard gate.** Auto-revert unlisted changes; block if revert fails |
| 3 | E003 | `Tests:` command passes |
| 4 | E004 | Commit message matches `Commit:` line |
| 5 | E018 | Token log entry exists with matching `task_id`, source=`agent`, non-zero tokens |
| 6 | E006 | Zero-output — at least one file has >0 diff |
| 7 | E017 | Excessive churn — net line changes < 3× estimate |
| 8 | E020 | Agent JSON output saved and parseable |
| 9 | E019 | No destructive git ops (`reset --hard`, `checkout --theirs/--ours`) in reflog |

Lattice memory: successful completions cached as attractors. Subsequent workers with matching file+test hash skip cold-path validation for steps 1, 3, 4.

## Attestation (`kanban_attestation.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_attestation.py <plan_id>                    # generate
python hermes-kanban-advanced-workflow/scripts/kanban_attestation.py <plan_id> --verify            # check validity
```

Generates `$HERMES_HOME/kanban/attestation.yaml` after preflight. Records: preflight status, profile validity, agent-prompt block count. Session-scoped (120 min TTL). Error codes: A001 (missing), A002 (stale), A003 (tampered).

## Card body policy (`kanban_card_policy.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py --all --profile balanced       # validate all cards
python hermes-kanban-advanced-workflow/scripts/kanban_card_policy.py <task_id>                      # validate one card
```

Validates card bodies against `policies/card-body-policy.yaml`. Error codes: P001 (missing Files:), P002 (missing agent block), P003 (missing Mode:), P004 (too many files), P005 (model override in card body). Resolves governance profile from `--profile`, `KANBAN_POLICY_PROFILE`, or `kanban-config.yaml` `policy_profile` (default `balanced`).

## Board-mediated handoff (`kanban_handoff.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_handoff.py --plan <plan.md>
python hermes-kanban-advanced-workflow/scripts/kanban_handoff.py --plan <plan.md> --plan-id <id> --allow-offline
```

Creates one hardened, idempotent orchestrator-handoff card when a non-orchestrator profile needs to trigger decomposition without a manual session switch.  The card title is `Decompose: <plan_id>` and carries `Type: orchestrator-handoff` — a governance carve-out that exempts it from the worker code-gen rules (P001/P002/P003).  The body is SOP-only: **no `agent -p` block** (to prevent auto-decompose into stub children).

Exit codes:

| Code | Meaning | Fix |
|------|---------|-----|
| 0 | Card created or already open | — |
| 2 | Orchestrator profile missing | `hermes kanban-advanced init` |
| 3 | Gateway not running | `hermes gateway run` |
| 4 | Dispatcher off or `auto_decompose=true` | Run the printed `hermes config set …` fix |

`--allow-offline` bypasses exit 3/4 to create the card anyway (for deferred dispatch). Idempotency: if an open handoff card for the same `plan_id` already exists, the script exits 0 without creating a duplicate.

## Recovery (`kanban_recover.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py <task_id> <error_code>             # single recovery
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --cascade                          # triage multi-failure
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --list                             # list all recovery actions
```

Maps the registry's 36 error codes to recovery actions — 10 have dedicated automated recovery functions (shown by `--list`); the rest surface the registry's documented recovery guidance for manual intervention. Cascade triage: pause downstream → env first → agent second → governance infra last → verify.

## Post-merge gate (`post_merge_gate.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/post_merge_gate.sh <plan_id>
```

Final audit gate. Runs after all cards complete: gate tests from the plan, cross-card regression check, excessive churn audit (E017). Do not close the board until this passes.

## Token tracking (`token_tracker.py`)

```python
from scripts.token_tracker import log_token_run, log_from_env, log_orchestrator_tokens
```

Writes `tokens.jsonl` entries for sprint budgeting.  `log_token_run()` for workers (cursor + hermes tokens), `log_from_env()` for env-driven logging, `log_orchestrator_tokens()` for orchestrator checkpoints.  E018 blocks cards without matching token entries.  E020 blocks cards where agent output wasn't captured.

## Postmortem generator (`generate_postmortem.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/generate_postmortem.py --plan-id <id> --output .hermes/kanban/reports/
```

Generates 8-section markdown postmortem: execution summary, agent performance, failure taxonomy, intervention log, discovered pitfalls, skill updates needed, token economics, learning summary. Reads `tokens.jsonl`, kanban SQLite DB, and intervention counter. Run before board archive.

## Verify optimization (`verify_optimization.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/verify_optimization.sh <plan>.md
```

Checks plan optimization readiness before decomposition: agent-prompt block count, Files:/Mode: lines, iteration budget estimates, dependency graph presence, line budget computed, sequential Card N labeling. Resolves governance profile from config/env; `--strict` or `strict` profile treats warnings as blocking.

## Commit reachability (`verify_commits_reachable.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/verify_commits_reachable.sh
```

Verifies every worktree commit is reachable from `${working_branch}` via merge or cherry-pick. Uses `-x` trailer from cherry-picks when direct ancestry fails.

## Governance integrity (`governance_integrity.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh
```

Pre-decomposition check: verifies all governance files (skills, scripts, registry, policies, prompts) exist and are intact. 30 checks total. Exit 1 if any file missing or non-executable.

## Intervention counter (`kanban_intervention_inc.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/kanban_intervention_inc.sh
```

Increments `.hermes/kanban/logs/interventions.count`. Called once per gateway escalation. Postmortem reads this counter for intervention rate KPI.

## Git safe cleanup (`git_safe_cleanup.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/git_safe_cleanup.sh --audit   # read-only inventory
bash hermes-kanban-advanced-workflow/scripts/git_safe_cleanup.sh --clean   # governed deletion
```

Post-execution git hygiene. `--audit` classifies every worktree/branch (protected, merged, kanban, fix, orphaned). `--clean` gates every destructive op on cleanliness + merge status. Never `--force` without `--dry-run` first.

## Worktree audit (`worktree_audit.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/worktree_audit.sh
```

Cross-references `git worktree list` with `hermes kanban list`. Classifies each worktree: safe-to-clean, needs-salvage, potential-loss, stale.

## Config validation (`validate_config.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/validate_config.py
```

Validates `kanban-config.yaml` overlay: required keys present, profiles exist, paths resolve.

## Goal card verification (`verify_goal_cards.py`)

```bash
python hermes-kanban-advanced-workflow/scripts/verify_goal_cards.py --plan <plan>.md
```

Verifies goal-card acceptance criteria, scenario tags, and budget limits before attestation.

## Anchor verification (`verify_anchors.sh`)

```bash
bash hermes-kanban-advanced-workflow/scripts/verify_anchors.sh
```

Verifies plan anchor points (line numbers, function names, file paths) against current HEAD.
