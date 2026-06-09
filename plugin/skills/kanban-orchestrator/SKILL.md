---
name: kanban-orchestrator
description: Decomposition playbook + anti-temptation rules + six-sigma audit for orchestrator profiles routing work through Kanban.
version: 5.4.0
metadata:
  hermes:
    tags: [kanban, multi-agent, orchestration, routing]
    related_skills: [kanban-advanced:kanban-worker]
---

# Kanban Orchestrator — Decomposition Playbook

> **Governance notice:** This skill sets procedural expectations. The governance layer (evaluation chain E001–E020, card body policy P001–P009, preflight.sh, validate_board.sh, pre_dispatch_gate.sh) structurally enforces them. If you hit a DENY or block, load `kanban-advanced:kanban-orchestrator-governance` for the error code reference and pitfall encyclopedia — do not guess.

> The core worker lifecycle (including the `kanban_create` fan-out pattern and the "decompose, don't execute" rule) is auto-injected into every kanban process via the `KANBAN_GUIDANCE` system-prompt block. This skill is the deeper playbook when you're an orchestrator profile whose whole job is routing.

## Role: Orchestrator

1. **Executive oversight** — ensure the kanban executes cleanly. Workers supervise agents; you supervise workers.
2. **Escalation handler** — workers escalate issues via heartbeat. Monitor via `watch` (primary, tmux pane) or cron (unattended fallback) and respond with investigation and fixes.
3. **Resource guard** — when a systemic issue is found, block affected tasks so time and tokens aren't wasted.
4. **Reconciliation lead** — findings that can wait are saved for post-plan reconciliation. Catastrophic issues are fixed immediately.
5. **Final audit** — the last task on every board. Reviews all work, runs tests, merges branches, gates the push.
6. **Proactive board manager** — do not wait for the operator to notice blocked cards. Poll the board continuously. When a card reaches `blocked`, investigate immediately. If it can be salvaged (iteration-limit with work done), salvage it. If it needs the operator, present the findings and the fix. A board with stagnant blocked cards is an orchestrator failure.
7. **Token attribution** — log orchestrator session tokens at every major checkpoint (planning complete, decomposition complete, audit start, cleanup complete). The orchestrator burns tokens during plan review, board monitoring, failure triage, and final audit — these must be attributed to the plan for sprint budgeting. See §Token attribution below.

## Token attribution (mandatory)

Every token the orchestrator burns during a plan run must be logged to `tokens.jsonl`. Workers handle their own logging (see `kanban-advanced:kanban-worker` §Token observability). The orchestrator logs at these checkpoints:

| Checkpoint | What to log | `plan_id` | `task_id` |
|-----------|-------------|-----------|-----------|
| Planning complete (after optimize) | Session tokens burned during plan review and hardening | `<plan_id>` | `""` (no task) |
| Decomposition complete (after gate) | Session tokens for card creation and linking | `<plan_id>` | `""` |
| Final audit start | Cumulative session tokens since decomposition | `<plan_id>` | `""` |
| Cleanup complete (after postmortem) | Cumulative session tokens for entire plan run | `<plan_id>` | `""` |

The orchestrator estimates its own token burn from turn count. If the session supports `/usage`, use the exact count. Otherwise estimate: `turns × 3000` tokens/turn (system prompt + tool schemas + kanban board context).

```python
# Call at each checkpoint from the orchestrator session:
import os, sys
sys.path.insert(0, os.environ.get("HERMES_KANBAN_REPO_ROOT", os.getcwd()))
from scripts.token_tracker import log_orchestrator_tokens

log_orchestrator_tokens(
    plan_id="<plan_id>",
    checkpoint="planning-complete",  # or decompose-complete, audit-start, cleanup-complete
    turns=15,  # estimated or from /usage
    note="Plan hardened and optimized. 13 agent-prompt blocks, 8-wave dependency graph."
)
```

**Why this matters:** Without orchestrator token attribution, sprint budgeting is blind to 30-50% of total token burn. The orchestrator's plan review, board monitoring, failure triage, and final audit can easily match or exceed the workers' cursor agent burn. Project managers need the full picture to budget tokens per sprint and scope project waterfalls.

## Monitoring: watch (primary) vs cron (fallback)

### Primary: `hermes kanban watch` in tmux

Live-stream all task events to a dedicated tmux pane.

```bash
tmux new-session -d -s kanban-watch -x 120 -y 30 \
  "hermes kanban watch --kinds completed,blocked,gave_up,crashed,timed_out --interval 1"
```

### Fallback: cron (unattended execution)

When the operator steps away, a 5-minute recurring cron checks heartbeats, staleness, and READY orchestrator tasks.

## Intervention notifications

When `watch` or cron surfaces a blocked, crashed, timed_out, or gave_up task, run this pipeline before paging the operator. Classify the event with **`kanban-advanced:kanban-notify`** — only rows in the intervention trigger table should reach the gateway; everything on the non-intervention list is handled silently.

### Flow (every intervention event)

1. **Pause the task.** Block the affected task (and the next `ready` successor when fixing shared environment state) so the dispatcher cannot stampede into a broken workspace:

```bash
hermes kanban block <task_id> "Paused — intervention triage in progress"
```

2. **Auto-retry if supported.** If the failure mode is on the **`kanban-advanced:kanban-notify` non-intervention list** (e.g. protocol violation with commits already present, expected reclaim cycle, transient vendor 429), unblock and let the dispatcher retry — do **not** notify:

```bash
hermes kanban unblock <task_id>
```

Wait one watch/cron tick and confirm heartbeats or completion before treating the retry as failed.

3. **Notify via gateway if retry fails.** When auto-retry is unsupported or a retry finishes without progress, compose the intervention message per **`kanban-advanced:kanban-notify`** (trigger label, task id, reason, suggested action) and deliver through the gateway operator chat channel. Prerequisites and delivery commands are in **`kanban-advanced:kanban-notify`** § Gateway delivery setup (`hermes gateway run` must be up — see Pitfalls).

Increment the intervention counter once per gateway escalation (feeds mid-run reconciliation). **This is mandatory — the postmortem reads this counter. Every intervention must be counted:**

```bash
bash hermes-kanban-advanced-workflow/scripts/kanban_intervention_inc.sh
# or from repo root: bash scripts/kanban_intervention_inc.sh
```

Verify the counter incremented: `cat .hermes/kanban/logs/interventions.count`

4. **Resume if auto-fix succeeds.** After Pass 2 triage fixes the root cause (or the operator replies with guidance), verify workspace state and tests, then unblock and confirm the task re-enters `running` or reaches `done` before clearing pauses on downstream tasks:

```bash
hermes kanban unblock <task_id>
```

**Operator boundary:** During walk-away execution, resolve every **`kanban-advanced:kanban-notify` non-intervention** event autonomously. Gateway notifications are reserved for intervention triggers the orchestrator cannot fix after one supported auto-retry.

## Profiles are user-configured — not a fixed roster

There is no default specialist roster. Before fanning out, ground the decomposition in the profiles that actually exist. The dispatcher silently fails to spawn unknown assignee names.

**Step 0: discover available profiles before planning.** Use `hermes profile list`. Cache the result.

## When to use the board (vs. just doing the work)

Create Kanban tasks when:
1. Multiple specialists are needed.
2. The work should survive a crash or restart.
3. The user might want to interject.
4. Multiple subtasks can run in parallel.
5. Review / iteration is expected.
6. The audit trail matters.

If none apply, use `delegate_task` or answer directly.

**Exception: self-referential governance plans.** When a plan modifies the kanban governance infrastructure itself — skill files, evaluation chain, validation scripts, board keeper, preflight, provisioning, or any script under `hermes-kanban-advanced-workflow/` — **execute manually rather than dispatching to workers.** The operator must experience each stage to verify the governance changes work as intended. Assign all workstreams to the primary persona (`${orchestrator_profile}`) and implement them sequentially. This ensures: (a) the edits correctly target the gaps they're meant to plug, (b) no dispatch infrastructure depends on files being modified mid-flight, and (c) the operator sees how each structural gate performs before relying on it. After implementation, run `provision.sh` to sync materialized skills, then `provision.sh --check` to verify sync.

## The anti-temptation rules

- **Do not execute the work yourself.**
- **For any concrete task, create a Kanban task and assign it.**
- **Split multi-lane requests before creating cards.** Extract independent workstreams first.
- **Run independent lanes in parallel.** Link only true data dependencies.
- **Never create dependent work as independent ready cards.** Pass `parents=[...]` in `kanban_create`.
- **If no specialist fits, ask the user which profile to create.**
This skill is the deeper playbook when you're an orchestrator profile whose whole job is routing.

**Interaction model:** The user moves through the workflow with explicit trigger phrases. Planning: `"Plan this out"` → `"Do a sanity check"` → `"Harden the plan"` → `"Optimize for Kanban"`. Execution: `"Execute the plan"`. Post-execution: the orchestrator MUST stop at each checkpoint and ask before proceeding. Never auto-advance.

### Post-execution checkpoint sequence (mandatory)

After the last implementation card completes and the final audit passes:

1. **Reconciliation checkpoint** — Present token burn, success rate, failure taxonomy. Ask: "Proceed to cleanup? Say yes."
2. **Cleanup checkpoint** — Remove crons, archive board, clean worktrees. Ask: "Proceed to postmortem? Say yes."
3. **Postmortem checkpoint** — Generate report, confirm all 8 sections. Present file path.

At each checkpoint the orchestrator MUST present findings and wait for the user's explicit "yes" before proceeding. Silently finishing or skipping checkpoints is a governance violation. See `plugin/data/references/interaction-model.md` for the full contract with exact phrasing and anti-patterns.

**Known vanilla hermes bugs:** See `references/vanilla-kanban-known-issues.md` — maps 12 upstream kanban bugs to structural workarounds. Load during Step 0b (Preflight) and apply fixes before decomposition.

**Governance sad-path audit:** See `references/governance-sad-path-audit.md` — full flowchart trace of every transition with 23 sad paths identified, governance coverage assessed, and gaps prioritized. Load during Step 0b to verify the plan's decomposition strategy covers every known failure mode.

## Decomposition choreography (Six Sigma)

### Pre-dispatch gate (replaces Steps 0a–0e)

A single script gates all pre-decomposition checks. Run before any card creation:

```bash
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

This runs in order: plan on `${working_branch}` → plan pushed → preflight → attestation → card policy present → plan memory seeded → DB integrity. Fails on any blocking check with a specific error.

After the gate passes, proceed directly to the Standard process. Plans may sit for hours or days while the user thinks them over. After the plan is optimized:

1. Present the optimization results.
2. Say: "Plan optimized. Ready when you are — say 'proceed' or 'execute' when you want me to decompose and dispatch."
3. **Stop. Wait. Do nothing.** No decomposition. No card creation. No triage.
4. Only proceed when the user says "go", "proceed", "execute", "decompose", or equivalent.

When ready, run the pre-dispatch gate — a single script that runs all checks (plan on `${working_branch}`, preflight, attestation, card policy, plan memory, DB integrity):

```bash
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

After the gate passes, proceed directly to Step 1. The gate replaces the old Steps 0a–0e.

### Full upgrade checklist

Preflight overrides set in the orchestrator's shell (e.g. `PREFLIGHT_PROFILES`, `PREFLIGHT_REQUIRED_SECRETS`) are **not** inherited by the gateway or workers. If preflight required overrides to pass, propagate them before dispatching:

```bash
# Option A: Export for the current gateway session
export PREFLIGHT_PROFILES="${worker_profile},default"
export PREFLIGHT_REQUIRED_SECRETS="***"
hermes gateway restart  # picks up new env

# Option B: Add to .hermes/.env for persistence across gateway restarts
echo "PREFLIGHT_PROFILES=${worker_profile},default" >> .hermes/.env
echo "PREFLIGHT_REQUIRED_SECRETS=*** >> .hermes/.env
```

Verify with `hermes kanban dispatch --dry-run --json` — check that `spawned[].assignee` lists the expected profiles and no `skipped_nonspawnable` entries appear for profile-not-found reasons.

## Hermes version-specific config (v0.15.0+)

Hermes Agent v0.15.0 (May 2026) introduced several kanban config keys that affect decomposition behavior. These must be set correctly **before** any board is dispatched, especially when running manual decomposition with custom providers.

### Critical: `auto_decompose` must be `false` for manual decomposition

v0.15.0 defaults `kanban.auto_decompose: true`. When enabled, the dispatcher auto-runs the decomposer on every triage task — producing a tree of stub children that **duplicate** manually-created cards. For manual decomposition workflows:

```bash
hermes config set kanban.auto_decompose false
```

Without this, triage tasks will be auto-decomposed and conflict with manually-structured boards.

### Critical: `kanban_decomposer` aux model for custom providers

v0.15.0 adds a new auxiliary task `kanban_decomposer` (like the existing `kanban_specifier`). For custom providers, `provider: auto` cannot resolve — the model must be set explicitly, same pattern as vision/compression/title_generation:

```bash
hermes config set auxiliary.kanban_decomposer.provider "custom:<provider-name>"
hermes config set auxiliary.kanban_decomposer.model "<full-model-id>"
```

Run this on every profile that may decompose tasks. The `base_url` and `api_key` inherit from the custom provider definition.

### New kanban config keys (v0.15.0)

| Key | Default | Purpose | Manual-decomp impact |
|---|---|---|---|
| `kanban.auto_decompose` | `true` | Auto-decompose triage tasks | **Set to `false`** |
| `kanban.auto_decompose_per_tick` | `3` | Max decompositions per dispatcher tick | Low — throttle only |
| `kanban.orchestrator_profile` | `""` (falls back to default) | Profile for triage decomposition | Set explicitly for clarity |
| `kanban.default_assignee` | `""` (falls back to default) | Fallback when decomposer can't match | Set explicitly |
| `kanban.failure_limit` | `2` | Auto-block after N consecutive failures | Already existed in v0.14.x |
| `kanban.dispatch_stale_timeout_seconds` | `14400` (4h) | Reclaim running tasks past heartbeat timeout | Our 3-min heartbeat is well within |
| `kanban.worker_log_rotate_bytes` | `2097152` (2 MiB) | Worker log rotation size | Default is fine |
| `kanban.worker_log_backup_count` | `1` | Worker log rotation backups | Default is fine |
| `auxiliary.kanban_decomposer` | `provider: auto, model: ""` | Model for decomposition | **Must configure for custom providers** |

### Stale `session_search` aux config cleanup

v0.15.0 rebuilt `session_search` to run without an auxiliary LLM (#27590). The `auxiliary.session_search.*` config block was removed from defaults. Existing configs with stale `session_search` entries are harmless (ignored), but `hermes config migrate` will flag them. Clean up with:

```bash
hermes config edit  # remove auxiliary.session_search block manually
```

Or they can be left as-is — the tool no longer reads them.

### Full upgrade checklist

See `references/hermes-v0.15.0-upgrade.md` for the step-by-step upgrade procedure covering: update, config migrate, aux model configuration, profile verification, stale config cleanup, and smoke testing.

### Step 1 — Understand the goal
Ask clarifying questions if ambiguous. Before sketching the task graph, work out what the plan needs to deliver, where each change belongs in the codebase, and whether any preferences can be deferred. Build the graph from what is needed first — optional improvements can be separate cards that drop if the budget runs short.

### Step 2 — Sketch the task graph
Draft the graph out loud before creating anything:
1. Extract lanes from the request.
2. Map each lane to a profile from Step 0.
3. Decide independent vs gated.
4. Create independent lanes as parallel cards.
5. Create synthesis/integration cards with parent links.

### Standard process (mandatory for every plan)

```
0. VERIFY DB integrity              python3 -c "import sqlite3; db=sqlite3.connect('$HERMES_HOME/kanban.db'); print(db.execute('PRAGMA integrity_check').fetchone()[0]); db.close()"
                                     Must return 'ok'. Remove stale init.lock if present.
1. CREATE root card                  hermes kanban create "<plan>" --assignee ${orchestrator_profile}
2. CREATE gate (blocked)            hermes kanban create gate --assignee ${orchestrator_profile}
                                     hermes kanban block <gate_id> "Gate — awaiting dependency links"
3. CREATE all implementation cards  Create independent cards as ready. Create dependent cards as ready,
   (STAGGERED)                      then immediately block before the dispatcher claims them.
                                     Stagger creates: ≥1s between cards, ≥3s pause every 5 cards.
                                     ALL implementation cards assigned to ${worker_profile} (worker profile).
                                     Gate, root, audit assigned to ${orchestrator_profile} (orchestrator profile).
4. CREATE final audit card          hermes kanban create "Final audit: <plan>" --assignee ${orchestrator_profile}
                                     hermes kanban block <audit_id> "Awaiting parent completion"
5. COMPLETE root immediately        hermes kanban complete <root_id> --summary "Root complete — N cards dispatched."
6. LINK all dependencies            hermes kanban link <parent> <child>
7. CREATE auto-unblock cron         cronjob(action="create", name="kanban-auto-unblock-1m",
                                      schedule="every 1m", deliver="origin", no_agent=true,
                                      repeat=999, script="scripts/auto_unblock.sh")
8. CREATE board keeper cron         cronjob(action="create", name="kanban-board-keeper-3m",
                                      schedule="every 3m", deliver="origin", no_agent=true,
                                      repeat=999, script="scripts/board_keeper.sh")
9. VERIFY both crons running        cronjob(action="list") — confirm both job_ids with
                                      next_run_at in the future
10. RUN validate_board.sh           bash hermes-kanban-advanced-workflow/scripts/validate_board.sh
                                      Full governance gate: cron health (scripts executable + hermes PATH +
                                      crons running), agent blocks, workspace isolation, parent links,
                                      dependency gating, test lines, budget heuristics.
11. UNBLOCK dependent cards         Unblock cards whose parents are done.
12. UNBLOCK gate                    Only after validate_board.sh passes.
13. COMPLETE gate immediately       hermes kanban complete <gate_id> --summary "Gate complete.
                                      Auto-unblock cron: <id>, Board keeper cron: <id>."
```

**Auto-progression (mandatory):** LLM orchestrators cannot poll the board autonomously — they only act when prompted. The mechanical work of "check parents → unblock children" and "salvage iteration-limit cards" must be delegated to scripts. The auto-unblock and board keeper crons are created as a mandatory hard gate in Steps 7–9 — crons are created and verified BEFORE validate_board.sh runs (Step 10), so the full governance gate includes cron health. The gate cannot complete until both crons are verified running AND validate_board.sh passes.

**Cron removal during cleanup:** Both crons must be removed during `kanban-advanced:kanban-cleanup`:

```bash
# Start auto-unblock — runs every 30s during execution
cronjob(action="create", name="kanban-auto-unblock-30s", schedule="every 30s",
  deliver="null", no_agent=true,
  script="scripts/auto_unblock.sh")
```

This script finds all blocked cards whose parents are done and unblocks them. It handles every wave transition without orchestrator intervention. The orchestrator still monitors for failures (via watch/cron), but wave progression is fully automated. Remove during cleanup.

**Profile assignment discipline (mandatory):**
- `${worker_profile}` → worker profile. ALL implementation cards. Must have `agent -p` block.
- `${orchestrator_profile}` → orchestrator profile. Root, gate, audit cards only. Must NOT have `agent -p` block (manual steps).
- Never assign an orchestrator card to a worker profile — the worker will spawn an agent with no work to do, and it will protocol-violate on every retry.

> **The final audit card is mandatory — not optional.** It gates on the last implementation card. When all implementation cards complete, the audit card auto-promotes and runs the full verification suite. Forgetting the audit card means the board completes with no verification. This happened on Phase 2 — the user had to remind us. Create it during decomposition, not after execution.

> **Never use `--triage` on the root card.** This assigns it to the orchestrator profile, which the dispatcher treats as a work card — triggering auto-decomposition into stub children that duplicate your manually-created cards. The root is a summary placeholder, not a work card. Complete it immediately after all children are created and linked.

### Goal-mode cards (vanilla `--goal`, Hermes ≥ 0.15.2)

Default: **one-shot** worker cards (no `--goal`). Use goal-mode only when the plan marks `goal_card: true` after Harden (see `references/goal-card-selection.md`, scenarios D1–D10). Plan-level cap: `goal_card_budget` (default **2**).

**Rules:**

- Read `goal_card`, `goal_max_turns`, and `goal_scenario` from plan frontmatter or section markers before `hermes kanban create`.
- Pass `--goal` and optional `--goal-max-turns N` only when `goal_card: true` for that workstream.
- Card body must lead with **`Acceptance:`** (judge criteria) then `Files:`, `Mode:`, and the `agent -p` block.
- **Never** `--goal` on root, gate, or final-audit cards (orchestrator profile).
- If a section is `goal_card: true` but splittable per anti-patterns A2/A7, **stop decomposition** and send the plan back to Revise — split instead of goal-mode.

```bash
hermes kanban create "integration-ci-green" \
  --assignee ${worker_profile} \
  --workspace "worktree:/tmp/wt-<plan>-<card>" \
  --branch "kanban/<plan>/<card>" \
  --goal \
  --goal-max-turns 18 \
  --body "Acceptance:
- Done when: <observable condition>
- Verify: <command>

Files: ...
Mode: modify-only

\`\`\`agent
agent -p \"...\"
\`\`\`"
```

Goal-mode uses the same Ralph-style judge loop as `/goal`; the evaluation chain still gates every `kanban_complete`. See `docs/how-to/goal-cards.md`.

### Decomposition granularity rule

Never bundle more than 2 distinct file-level changes per card. A card with 3+ sub-tasks across multiple files overruns the agent's context window and causes dropped sub-tasks. Split coarse decomposed cards manually.

### Card body format — `Files:` and `Mode:` lines are mandatory

Every code-generation card body must include:

1. **`Files:`** line — lists every file the agent must touch.
2. **`Mode:`** line — declares the expected file operation:
   - **`modify-only`** — file must already exist; agent edits in-place.
   - **`create-only`** — file must not exist; agent creates it.
   - **`any`** — file may exist or not; agent handles either case.
3. **`--workspace`** — must be `worktree:<absolute-path>` for every code-gen card. Use `/tmp/wt-<plan>-<card>` per card (e.g. `/tmp/wt-curious-ws1`). Never use the main repo path (causes workspace contention). Never use relative paths — `worktree:.` is **rejected** by the dispatcher (error: "non-absolute worktree path"). Never omit `--workspace` (defaults to `scratch` — zero output). The only exception is report generation with no codebase dependency.

```
agent -p "Implement [task] per plan §[section].
Files: path/to/file1.py, path/to/file2.py.
Mode: modify-only.
Tests: <test command>.
Commit: <commit message>.
Do NOT push to ${working_branch} — commit to worktree branch only."
```

> **Model selection belongs to the profile, not the card body.** Do NOT add `--model` or `--output-format` flags. The profile's `config.yaml` determines the model. Card body policy P005 (MODEL_OVERRIDES_PROFILE) blocks cards that attempt to override profile model config at dispatch.

When creating the card via CLI (add `--goal` / `--goal-max-turns` only when plan says `goal_card: true`):

```
hermes kanban create "card-name" \
  --assignee ${worker_profile} \
  --workspace "worktree:/tmp/wt-<plan>-<card>" \
  --branch "kanban/card-name" \
  --body "..."
```

> **Never use relative paths like `worktree:.`.** The dispatcher rejects non-absolute worktree paths with "workspace: task has non-absolute worktree path." Always use an absolute path with the `worktree:` prefix (e.g. `worktree:/tmp/wt-curious-ws1`).

If a code-gen card is created with `scratch` workspace, the worker must block it immediately. The agent will not find the repo and will produce zero changes.

## Branch model

The branch model controls where agent commits land and when CI builds are triggered. These are project-configured values (see `kanban-config.yaml`):

| Variable | Default | Meaning |
|---|---|---|
| `${working_branch}` | overlay | Integration branch; orchestrator merges completed sections here |
| `trigger_branch` | overlay (optional) | Protected deploy branch; when set, agents must not push here (E009) |
| `kanban/` | `kanban/` | Prefix for per-section feature branches |

**Rule:** Workers commit and push to their feature branch (`kanban/<plan>/<section>`), never to `${working_branch}`. The orchestrator merges completed sections into `${working_branch}` during the final audit. When `trigger_branch` is set in `kanban-config.yaml`, only the operator manually merges `${working_branch}` → that branch to trigger a build.

**Why separate?** When `trigger_branch` is set, keeping it distinct from `${working_branch}` lets agent commits integrate without firing deploy CI on every push. Omit `trigger_branch` in `kanban-config.yaml` if you do not use a separate protected deploy branch.

**Commit cadence:** Merge incrementally as each card completes — do NOT wait for the final audit. After each card reaches `done`, the orchestrator must immediately fetch the commit from the worktree and merge to `${working_branch}`. The dispatcher and board keeper clean worktrees on their own schedule — if a worktree is removed before the commit is merged, the commit is lost. Recovery is sometimes possible from orphaned worktrees on disk (see Final Audit § step 2), but not guaranteed.

**Cherry-pick traceability (mandatory):** Always use `-x` when cherry-picking commits to staging. This appends a `(cherry picked from commit <sha>)` trailer to the commit message, creating a permanent audit trail from staging back to the worktree source.

```bash
# Canonical staging-integration pattern — mandatory -x flag:
git cherry-pick -x "$commit" --no-edit
```

Without `-x`, the cherry-picked commit gets a new SHA with no link to the original. `verify_commits_reachable.sh` relies on the trailer when direct ancestry (`git merge-base --is-ancestor`) fails because the SHA differs. Cherry-pick without `-x` is a final-audit finding — the operator must manually verify traceability.

**Integration freshness — same-file parent-child cards:** When a card is linked to a parent that touched the same file(s), the child's worktree base may be stale if staging advanced with other commits after the parent completed. Cards with same-file parent-child links should enforce a maximum gap: if a child is promoted more than 1 hour after its parent completed, the worker must merge `origin/${working_branch}` (not just the parent branch) before spawning the agent. See `kanban-advanced:kanban-worker` § Integration freshness check.

## Salvage pattern (iteration-limit recovery)

When a card is blocked with "Iteration budget exhausted (90/90)" but the agent completed the work (files exist, git diff shows changes, sometimes even committed), salvage instead of retrying:

**Detection:** `hermes kanban show <id>` shows iteration-limit block. Check the worktree:
```bash
ls -la <worktree>/backend/app/services/<new_module>.py  # file exists?
git -C <worktree> log --oneline -3                      # commit exists?
git -C <worktree> diff --stat                            # uncommitted changes?
```

**Salvage flow (committed):**
```bash
# 1. Fetch the commit from the worktree
git fetch <worktree> <branch>
# 2. Merge to ${working_branch}
git merge FETCH_HEAD --no-edit
# 3. Complete the card
hermes kanban complete <id> --summary "WS<N> shipped: <what was done>."
```

**Salvage flow (uncommitted):**
```bash
# 1. Commit on the worktree
cd <worktree> && git add -A && git commit -m "feat: <description>"
# 2. Fetch and merge as above
cd <main-repo> && git fetch <worktree> <branch> && git merge FETCH_HEAD
# 3. Complete the card
```

**When NOT to salvage:** If no files were created or `git diff` is empty, the agent produced nothing — retry or split the card.

**Root cause:** Card too large for 90-turn budget. Apply the iteration budget ceiling (35 turns — see `kanban-advanced:kanban-planning` §Optimize checklist item 3) before the next decomposition. Salvage is a recovery pattern, not a substitute for correct card sizing.

## Escalation hierarchy — when the coding agent fails

When a coding agent cannot complete a card (workspace trust, auth, timeout, crash, zero output), follow this escalation path. **Never jump directly to `kanban_complete` on an unimplemented card.**

```
Coding agent fails
        │
        ▼
1st resort: FIX ENVIRONMENT + RETRY
   Worker fixes the root cause (pre-trust workspace, verify auth,
   recreate worktree) and re-dispatches. Agent tries again.
   ✓ Least governance bypass — eval chain runs normally.
        │ (if retry also fails)
        ▼
2nd resort: WORKER IMPLEMENTS DIRECTLY
   Worker writes the code, runs tests, commits, and runs the FULL
   evaluation chain (E001–E020). Worker plays both roles: implementer
   and verifier.
   ✓ Eval chain still runs — log tokens with source="worker-direct".
        │ (if worker cannot implement — wrong skill set, infra-only)
        ▼
3rd resort (LAST): ORCHESTRATOR IMPLEMENTS
   Orchestrator writes the code, commits, runs the FULL evaluation
   chain, cherry-picks to staging, and completes the card.
   Orchestrator plays three roles: coding agent + worker + orchestrator.
   ✓ Eval chain MUST run before kanban_complete.
   ✗ Flag in postmortem — two levels of escalation failed.
```

**Rule 1 — Never bypass the eval chain (applies to ALL roles):** Whoever completes the card — coding agent, worker, or orchestrator — MUST run the evaluation chain before `kanban_complete`. The chain is the governance layer's enforcement mechanism. Bypassing it is a protocol violation regardless of who did the implementation.

```bash
# Required before any kanban_complete on a code-gen card:
python hermes-kanban-advanced-workflow/scripts/kanban_evaluation_chain.py <task_id> <workspace>
# Must return: EVALUATION CHAIN PASSED
```

If no coding agent ran (worker-direct or orchestrator-direct), log tokens with the appropriate source:

```python
from scripts.token_tracker import log_from_env
log_from_env(
    plan_id=os.environ["HERMES_KANBAN_PLAN_ID"],
    turns=N,
    cursor_input_tokens=0,
    cursor_output_tokens=0,
    source="worker-direct",  # or "orchestrator-direct"
)
```

**Rule 2 — Zero-output guard:** E006 (zero output) applies to ALL completions. If the card's `Files:` show zero changes in `git diff --stat HEAD~1`, the card CANNOT be completed — regardless of who did the work. The only exception is cards explicitly scoped as "verification only" or "read-only" in the plan body.

**Rule 3 — Document escalation in postmortem:** Any card completed at the 2nd or 3rd resort level must be flagged with: which resort level, why the coding agent failed (root cause), whether the governance chain ran (must be "yes"), and the token source tag.

## Common patterns

**Fan-out + fan-in:** N `researcher` tasks with no parents, one `analyst` task with all of them as parents.

**Pipeline with gates:** `pm → implementer → reviewer`. Each stage's `parents=[previous_task]`.

**Same-profile queue:** 50 tasks, all same assignee, no dependencies. Dispatcher serializes.

**Human-in-the-loop:** Any task can `kanban_block()` to wait for input.

**Final-audit card:** Always create after decomposition with the last plan task as parent.

## Final audit (mandatory)

After all tasks reach `done`:

**The final audit is orchestrator-executed, not dispatched to workers.** The audit card body is a text checklist — it has no `agent -p` block. Any worker that picks it up will protocol-violate (same failure mode as the gate card). Create the audit card as a placeholder for the board's dependency graph (it gates on the last implementation card), but when it reaches `ready`, the orchestrator runs the audit directly and completes the card manually.
## Final audit (mandatory)

After all tasks reach `done`:

1. **File-level plan compliance:** `git diff --stat <baseline>..HEAD` — verify every planned file has > 0 lines changed. Zero-diff = dropped sub-task.
2. **Lint + typecheck** on changed files.
3. **Full test suite.**
4. **Post-merge gate:** Run `bash hermes-kanban-advanced-workflow/scripts/post_merge_gate.sh <plan_id>` — this verifies gate tests from the plan, cross-card regression, and churn audit. Do not close the board until this passes.
4. **Cross-task consistency** — merge conflicts, line counts, schema drift.
5. **Git log review** — all commits present, no revert chains.
6. **Push + monitor CI** until green.
7. **KPI data integrity (mandatory):** Before running postmortem, verify all three data sources exist:
   - Token log: `python3 -c "from pathlib import Path; p=Path('.hermes/kanban/tokens.jsonl'); print('OK' if p.exists() else 'MISSING: token log — workers did not call log_token_run()')"`
   - Kanban DB: `test -f "$HERMES_HOME/kanban.db" && echo "OK" || echo "MISSING: kanban.db"`
   - Intervention counter: `test -f .hermes/kanban/logs/interventions.count && echo "OK ($(cat .hermes/kanban/logs/interventions.count))" || echo "MISSING: interventions.count"`
   If any source is missing: flag in postmortem, investigate which worker/script didn't write it, harden the gap. Do NOT skip KPI reporting because of missing data — estimate from agent logs.
   8. **Cross-card regression check (E017):** When multiple cards touched the same file, verify that functions added by earlier cards are still present after later merges. Card 10 removed `_merge_fetch_scope_exhausted` that Card 2 added — both touched `tinyfish_pipelines.py`, the dependency chain was respected, but the merge was destructive. For each file touched by ≥2 cards, diff the first card's additions against the final merged state and flag any function that was added then removed.
   9. **Gate test verification:** Before marking the plan complete, verify every gate test from the plan's Test plan section passes. Do not trust plan YAML alone — this plan's Card 1 was marked `completed` while the harness test was red on HEAD. Run the plan's specified gate tests and only mark the plan done when they pass.
   10. **Excessive churn audit:** For each card, compare actual line changes (additions + deletions) against the plan's estimated line budget. Flag any card that exceeds the estimate by >3×. Card 5 produced 8,551 net line changes on `tinyfish.py` against an estimated ~30 — this was a whole-module rewrite not in plan scope.

**KPI reporting (mandatory for postmortem):** Every postmortem must include token burn (orchestrator + worker + CLI agent, by provider), cache efficiency, cost estimate, success rate, autonomous completion rate, first-pass yield, intervention rate, wall clock duration, and failure-mode distribution. If token_tracker.py was not configured, estimate from agent logs (grep 'API call' agent.log). The user will ask for KPIs — have them ready.

## Walk-away mode

When the operator says **"walk away"**, **"go unattended"**, or equivalent after plan optimization, switch from interactive oversight to unattended execution. Walk-away treats **proceed** and **walk away** as the same user gate (Step 0) — both authorize decomposition; walk-away additionally arms monitoring, auto-retry, and gateway notifications.

### Walk-away checklist (run in order)

1. **Preflight** — Run Step 0b before any card creation. On `fail`, stop and do not enter walk-away. On `degraded`, require explicit operator OK. See **`kanban-advanced:kanban-preflight`**.

```bash
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
```

2. **Decompose and dispatch** — Execute the standard process (root → gate → decompose → same-file links → unblock gate). Include the mandatory final-audit card. Do not execute worker tasks yourself.

3. **Enable auto-retry** — Walk-away assumes the **Intervention notifications** pipeline is active for every `blocked`, `crashed`, `timed_out`, or `gave_up` event:
   - Pause (`kanban block`) before triage.
   - **Auto-retry once** when the failure is on the **`kanban-advanced:kanban-notify` non-intervention list** or the plan sad-path table marks it retryable.
   - Gateway notify only after retry exhaustion or non-retryable triggers.
   - Resolve non-intervention events autonomously — do not page the operator for routine recoveries.

4. **Set up board keeper cron** — The board keeper runs every 3 minutes and actively manages the board (salvages iteration-limit cards, kills orphans, merges worktrees, cleans stale worktrees, detects stuck dispatchers). Create at board start; remove during cleanup. See `scripts/board_keeper.sh`.

```bash
# Example: Hermes cron (use deliver="null" so the job persists — see Pitfalls)
cronjob(action="create", name="kanban-monitor-300s", schedule="every 5m",
  prompt="Poll board: heartbeats, staleness, blocked/crashed/timed_out/gave_up.
  Apply kanban-advanced:kanban-notify trigger table. Triage per Intervention notifications.
  If zero running and zero ready tasks, emit completion signal for orchestrator cleanup.")
```

The cron must apply the same intervention rules as **`hermes kanban watch`** (see § Monitoring). Poll for READY orchestrator tasks (e.g. final-audit card) and print **AUDIT READY** when the audit task is waiting. If chat delivery fails for ~two consecutive ticks, fall back to log inspection per **`kanban-advanced:kanban-notify`** § Walk-away cron.

Kill the tmux watch session if one was started interactively — cron is the unattended primary:

```bash
tmux kill-session -t kanban-watch 2>/dev/null || true
```

5. **Confirm notification channel** — Before the operator leaves, load **`kanban-advanced:kanban-notify`** and verify gateway delivery:
   - `hermes gateway run` (or already running per preflight)
   - `hermes gateway status` passes
   - Operator chat channel configured in Hermes config
   - Send a **test intervention-shaped message** and confirm receipt
   - State the **8 intervention triggers**, **7 silent events**, and whether `NOTIFY_ON_COMPLETE` is set (handoff script in **`kanban-advanced:kanban-notify`**)

Optional: `hermes kanban notify-subscribe <audit_task_id>` for instant audit-ready ping.

6. **Handle completion** — When all worker tasks reach `done`:
   - Run **Final audit (mandatory)** on the orchestrator profile.
   - Run **`kanban-advanced:kanban-reconciliation`** if intervention ratio exceeded thresholds mid-run.
   - Run **`kanban-advanced:kanban-cleanup`** (postmortem generation, board archive) — see **`kanban-advanced:kanban-postmortem`** / cleanup skill.
   - Remove monitoring cron (`cronjob(action="remove", job_id="<id>")`).
   - Complete the stranded root card if it auto-promoted to `ready`.
   - Send completion notification per **`kanban-advanced:kanban-notify`** after postmortem is written (on by default; set `NOTIFY_ON_COMPLETE=false` to suppress).

**Operator boundary (walk-away):** Gateway pages are for true manual interventions only. Everything else — progress, heartbeats, successful auto-retry, non-intervention blocks — stays silent unless completion notify is opted in.

## Walk-away monitoring

Cron-focused supervisor for unattended walk-away. Create at board start (Walk-away checklist step 4); remove during reconciliation/cleanup. Prefer over tmux `watch` when the operator session may end.

### Purpose

**5-minute** recurring Hermes cron polls the board while walk-away runs — heartbeats, failures, READY orchestrator cards, completion — without an operator at the keyboard.

### What to poll

Each tick via `hermes kanban list` (and `hermes kanban show <task_id>` for triage):

- **Heartbeats** — stale `kanban_heartbeat` on running tasks.
- **Staleness** — running tasks past reclaim / progress thresholds.
- **Failure states** — `blocked`, `crashed`, `timed_out`, `gave_up` (same kinds as `hermes kanban watch`).
- **READY orchestrator tasks** — e.g. final-audit card assigned to the orchestrator profile.

### Intervention rules

Same pipeline as § Intervention notifications and the **`kanban-advanced:kanban-notify` intervention trigger table**:

1. **Classify** — trigger row vs non-intervention list.
2. **Pause** — `hermes kanban block <task_id>`.
3. **Auto-retry once** — unblock retryable / non-intervention failures; stay silent on success.
4. **Gateway notify** — operator page only after retry exhaustion or non-retryable triggers (`missing_profile`, `auth_failure`, …). See **`kanban-advanced:kanban-notify`** § Gateway delivery setup. Run `kanban_intervention_inc.sh` per escalation.

### Completion detection

- **Plan complete** — zero running (●) and zero ready (▶): emit a **completion signal** (counts) for orchestrator final audit + cleanup. Do not self-remove the cron inside the tick.
- **Audit waiting** — orchestrator card in `ready`: print **`AUDIT READY — <task_id> is waiting`**. Optional: `hermes kanban notify-subscribe <audit_task_id>`.

### Chat delivery fallback

If chat delivery fails for **~two consecutive ticks** (~10 min), inspect logs per **`kanban-advanced:kanban-notify`** § Walk-away cron:

```bash
bash scripts/kanban_cron_monitor_log_fallback.sh
tail -30 "${KANBAN_CRON_LOG_DIR:-$HERMES_HOME/kanban/logs}/cron-monitor.log"
```

Fresh log lines without matching chat → fix `deliver`/routing; the poll still ran.

### Cleanup

Remove during **`kanban-advanced:kanban-reconciliation`** / **`kanban-advanced:kanban-cleanup`** — a completion banner is not removal:

```bash
cronjob(action="remove", job_id="<id>")   # id from cronjob(action="list") at create time
```

### Example cronjob call

`no_agent=true` + shell poll; **`deliver="null"`** so the job persists (Pitfalls).

```bash
cronjob(action="create", name="kanban-monitor-300s", schedule="every 5m",
  deliver="null", no_agent=true,
  command=<<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
LIST="$(hermes kanban list 2>&1)"
RUNNING=$(echo "$LIST" | grep -c '●' || true); READY=$(echo "$LIST" | grep -c '▶' || true)
echo "$LIST"
# kanban-advanced:kanban-notify: block → auto-retry once → gateway if exhausted
for id in $(echo "$LIST" | awk '/blocked|crashed|timed_out|gave_up/ {print $2}'); do hermes kanban show "$id" | head -15; done
echo "$LIST" | grep '▶' | grep -i orchestrator && echo "AUDIT READY — see ready line above"
[ "$RUNNING" -eq 0 ] && [ "$READY" -eq 0 ] && echo "KANBAN_COMPLETE — run final audit + cleanup"
bash scripts/kanban_cron_monitor_log_fallback.sh 2>/dev/null || true
SCRIPT
)
cronjob(action="list")   # verify next_run_at; store job_id for remove
```

## Salvage pattern

When a card hits the iteration limit but completed its extraction work, the orchestrator can recover it without re-running the agent. See `references/salvage-pattern-iteration-exhausted-cards.md` for the full procedure.

## Pitfalls

> **Full pitfall encyclopedia → `kanban-advanced:kanban-orchestrator-governance`.** The evaluation chain (E001–E020) and card body policy (P001–P009) structurally enforce the most critical rules. Load the governance reference skill when you need detailed diagnostics and historical context for a specific pitfall.

**Key procedural pitfalls (see governance ref for full context):**
- `auto_decompose: true` creates duplicate children — set to `false`.
- Gateway must be running for dispatch.
- SQLite torn-extend from rapid writes — stagger creates ≥1s apart.
- Iteration-limit blocked cards often have committed work — salvage, don't re-dispatch.
- Workspace paths must be absolute and unique (`worktree:/tmp/wt-<plan>-<card>`).
- Cherry-pick without `-x` breaks traceability — always use `-x`.
- Never complete a card without running the evaluation chain (E001–E020).
- **Canonical-first rule:** edit canonical source → `provision.sh` → `provision.sh --check`.
