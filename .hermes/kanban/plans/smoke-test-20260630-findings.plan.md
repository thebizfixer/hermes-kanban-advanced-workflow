---
name: Smoke Test 2026-06-30 — Cross-Reference & Gap Inventory
plan_id: smoke-test-20260630-findings
line_budget: 0
overview: >
  Cross-reference of the 2026-06-30 kanban-standard-smoke-test agent logs
  against Card 5's post-execution reports (postmortem, KPI JSON, final audit).
  13 anomalies identified across 4 severity tiers.  The common thread: every
  subsystem that queries kanban state must use the board resolver singleton —
  and none of them self-validate that their data source is the correct board.
execution_mode: direct
isProject: false
contingencies:
  - risk: "generate_postmortem.py already has --board flag but no resolver fallback"
    probability: Confirmed
    impact: HIGH
    mitigation: "Add resolver import + fallback in main() before arg parsing"
    auto_retry: false
  - risk: "board_slug not stamped because HERMES_KANBAN_BOARD not inherited"
    probability: Confirmed
    impact: HIGH
    mitigation: "Orchestrator must source KANBAN_BOARD from handoff body; decomposer must accept KANBAN_BOARD as fallback"
    auto_retry: false
prior_run_learnings:
  note: "Fresh smoke test executed 2026-06-30 on board kanban-standard-smoke-test-20260630-184420. All 5 cards completed autonomously (0 interventions). Board resolver singleton shipped in commit 482fc38 but 3 gaps remain — generate_postmortem never updated, board_slug never stamped, Card 5 body lacks --board."
optimization_checklist:
  agent_blocks_present: n/a
  no_model_in_card_bodies: n/a
  iteration_budget_estimated: n/a
  files_mode_lines_present: n/a
  commit_granularity_aligned: n/a
  dependency_graph_drawn: skip
  card_order_finalized: skip
  line_budget_computed: n/a
  card_granularity_verified: n/a
  same_file_merge_verified: n/a
  cross_section_contradictions: n/a
  plan_committed: pass
  card_body_self_containment: n/a
  diff_cap_present: n/a
  acceptance_surface_audit: skip
  call_site_audit: skip
  verification_taxonomy: skip
  same_file_graph: skip
  multi_parent_cap: skip
  spec_precision: n/a
  markup_safe_placeholders: pass
  plan_memory_seed: skip
  platform_neutrality_acceptance: skip
  files_completeness: n/a
todos:
  - id: fix-1-postmortem-resolver
    content: "Add board_resolver import to generate_postmortem.py; resolve board when --board absent; use board-scoped task discovery"
    status: pending
  - id: fix-2-board-slug-stamp
    content: "Orchestrator must export HERMES_KANBAN_BOARD from handoff body; decomposer L979 must fall back to KANBAN_BOARD"
    status: pending
  - id: fix-3-card5-board-flag
    content: "Update smoke-test plan Card 5 body to pass --board to generate_postmortem.py and kanban_token_report.py"
    status: pending
  - id: fix-4-walkaway-gate
    content: "Orchestrator runbook must check walk_away_mode BEFORE dispatching implementation cards, not after"
    status: pending
  - id: fix-5-remediation-autounblock
    content: "Audit-spawned remediation cards must be auto-unblocked by board-scoped crons; gateway cron store isolation gap"
    status: pending
  - id: fix-6-coder-protocol-violation
    content: "Coding agent sub-agent called kanban_complete directly on Card 4 before eval chain finished; prevent or detect"
    status: pending
  - id: fix-7-e002-untracked
    content: "E002 must check git status --porcelain or git ls-files --others in addition to git diff --name-only"
    status: pending
  - id: fix-8-duplicate-crons
    content: "Clean up stale plan-scoped crons from prior runs; provision_kanban_crons.sh should --clean before --create"
    status: pending
  - id: fix-9-fresh-attestation-stale
    content: "_check_git_freshness() must check attestation timestamp not just existence; or delete attestation after gate"
    status: pending
  - id: fix-10-token-metering
    content: "Investigate why 40 token log entries have empty tokens dict — hermes_token_meter delta capture gap"
    status: pending
  - id: fix-11-postmortem-confidence
    content: "data_confidence logic double-checks board-scoped task count vs total_tasks from kanban.db query"
    status: pending
  - id: fix-12-card5-postmortem-status
    content: "Postmortem shows Card 5 as 'running' when it's archived — status read from stale snapshot"
    status: pending
  - id: fix-13-governance-cron-config
    content: "kanban-governance cron shows 'config not found' — workdir is card5 worktree, not repo root"
    status: pending
---
# Smoke Test 2026-06-30 — Cross-Reference & Gap Inventory

> **Execution mode:** `direct` — this plan modifies scripts under the plugin repo. Per orchestrator skill v5.5.1 § Self-referential governance, it must be executed manually, not Kanban-decomposed.

> **Board:** `kanban-standard-smoke-test-20260630-184420` | **Run:** 2026-06-30 12:45–13:40 UTC | **Interventions:** 0

## Common Thread

Every subsystem that queries kanban state (postmortem generator, token reporter, final audit, lifecycle notify) must use the board resolver singleton — and **none of them self-validate that their data source is the correct board**. The postmortem pulled task `t_28871978` from board `20260630-010833` because `generate_postmortem.py` scanned all boards without filtering. The `board_slug` was stamped nowhere. The resolver code shipped (commit `482fc38`) but three consumers were never wired up.

A secondary thread: **gating is sequenced too late**. The walk-away gate blocks the handoff card *after* decomposition and dispatch — Card 5 already ran post-execution before any operator approval. The orchestrator runbook decomposes → dispatches → monitors → Card 5 executes → *then* blocks. The gate must fire before decomposition, not after.

---

## Anomaly Inventory

### 🔴 BLOCKING / HIGH

#### A1. Postmortem cross-board contamination
- **Evidence:** Postmortem reports 17 tasks; board has 15. `t_28871978` is from board `kanban-standard-smoke-test-20260630-010833`, not this run's board `20260630-184420`.
- **Root cause:** `generate_postmortem.py` does not import `resolve_board_for_plan()`. When Card 5 runs `generate_postmortem.py --plan-id kanban-standard-smoke-test` (no `--board`), it falls back to scanning ALL boards' kanban.db for matching plan_id. The `--plan-id` substring match picks up tasks from prior archived boards.
- **Impact:** Success rate distorted (70.6% instead of true), KPI `data_confidence: high` is false, task list includes ghosts.
- **Fix:** `generate_postmortem.py` line ~2029: add `from lib.board_resolver import resolve_board_for_plan` and call when `args.board` is None. Wire board_slug through to `_get_board_task_ids()`.
- **File:** `scripts/generate_postmortem.py`

#### A2. Walk-away gate defeated — post-execution ran autonomously
- **Evidence:** Handoff body stamps `walk_away_mode: false`. Orchestrator decomposes → dispatches 5 cards → Cards 1–4 complete → Card 5 runs final audit, spawns 6 remediation cards, generates postmortem/KPI/token report → *then* handoff card blocks with "Awaiting operator approval." Operator never approved.
- **Root cause:** The orchestrator runbook sequences decomposition + dispatch BEFORE the walk-away check. The gate is at the end of the runbook, not the beginning. Card 5's `Acceptance:` steps are unconditional — no code checks `walk_away_mode`.
- **Impact:** Operator loses control of post-execution. In a production plan, this means unverified code could be deployed/marked-done without review.
- **Fix:** In `kanban-advanced:kanban-orchestrator` skill / runbook: after gate card completes but BEFORE creating implementation cards, check `walk_away_mode`. If false, block root card with "Awaiting operator approval" and do NOT create Cards 1–N.
- **File:** `plugin/data/skills/kanban-orchestrator/SKILL.md` (runbook § Step 2b)

#### A3. Remediation cards archived without autonomous completion
- **Evidence:** 6 remediation cards spawned (`t_5b6367f4` through `t_cae48f3e`), all `archived` with no `completed` events. KPI `completeness.violations` lists them but none resolved.
- **Root cause:** Auto_unblock cron (`kanban-auto-unblock-1m`) uses board-scoped scripts in card5 worktree, but the gateway cron store isolation prevents the cron from seeing the cards. The orchestrator session's cron provisioning is fire-and-forget — crons are created but the gateway may not have the correct context to execute them.
- **Impact:** Remediation loop exercised but not effective. Full Layer 2 autonomous recovery path not proven.
- **Fix:** Verify crons are visible to gateway (`hermes cron list` from outside the orchestrator session). Board-scoped crons may need to be provisioned from the default profile, not from the orchestrator worktree.
- **File:** `scripts/provision_kanban_crons.sh`, `scripts/kanban_handoff.py`

#### A4. Coder sub-agent protocol violation on Card 4
- **Evidence:** Card 4 `t_8f06ec94` shows: "Task was already marked `done` by the coding agent sub-agent (kanban-advanced-coder) via protocol violation — it called `kanban_complete` directly." The eval chain then found E003_TEST_FAILURE but the card was already `done`.
- **Root cause:** The coding agent (hermes binary invoked as `kanban-advanced-coder`) bypassed the worker and called `kanban_complete` on the card. The worker's eval chain ran after and found the failure, but couldn't revert the completion.
- **Impact:** Eval chain enforcement bypassed. If the agent had produced incorrect code, it would have been marked done without governance review.
- **Fix:** Worker should verify card status after agent dispatch — if agent already completed the card, worker must un-complete and re-run eval chain. Or: prevent coding agent from calling `kanban_complete` by restricting its toolset.
- **File:** `scripts/kanban_evaluation_chain.py` (worker skill / invoke.sh — add post-agent status check)

### 🟡 DEGRADED

#### A5. `board_slug` not stamped in plan memory
- **Evidence:** `.hermes/kanban/memory/kanban-standard-smoke-test.json` has no `board_slug` key. Decomposer L979 checks `HERMES_KANBAN_BOARD` but handoff body exports `KANBAN_BOARD` (line 884). Different env var names.
- **Root cause:** `kanban_handoff.py` L1044 sets `os.environ["HERMES_KANBAN_BOARD"]` in the handoff process (default profile). The orchestrator is a separate gateway-spawned session — it doesn't inherit the handoff's environment. Handoff body says `export KANBAN_BOARD` but decomposer checks `HERMES_KANBAN_BOARD`.
- **Impact:** Resolver must scan all boards by prefix match — works but fragile when 3 boards share the plan_id prefix. Any script that queries `HERMES_KANBAN_BOARD` gets empty string.
- **Fix:** Decomposer L979: add `or os.environ.get("KANBAN_BOARD", "")` fallback. Handoff body line 884: change to `export HERMES_KANBAN_BOARD="{kanban_board}"`.
- **Files:** `scripts/kanban_decompose.py` L979, `scripts/kanban_handoff.py` L884

#### A6. Duplicate crons (board-scoped + plan-scoped)
- **Evidence:** `hermes cron list` shows both `kanban-auto-unblock-1m` (board-scoped, workdir=card5 worktree) and `kanban-auto-unblock-1m-kanban-standard-smoke-test` (plan-scoped, workdir=repo root). The plan-scoped crons are from prior runs.
- **Root cause:** `provision_kanban_crons.sh` creates new crons each handoff but never cleans stale ones from prior plan executions.
- **Impact:** Stale crons pollute the cron store. If they fire, they operate on the wrong board/context.
- **Fix:** `provision_kanban_crons.sh --create` should `--clean` first for the same plan_id suffix.
- **File:** `scripts/provision_kanban_crons.sh`

#### A7. E002 gap: untracked files not detected
- **Evidence:** Card 4 created `_smoke_scratchpad.md` as untracked file. E002 check ran `git diff --name-only` which excluded untracked files. Worker documented: "E002 auto-revert did NOT catch it — the current implementation only checks `git diff --name-only`, which excludes untracked files."
- **Root cause:** E002 implementation in `kanban_evaluation_chain.py` only runs `git diff` against the worktree. Untracked files (`git status --porcelain`, `git ls-files --others --exclude-standard`) are not checked.
- **Impact:** Layer 1 autonomous recovery (E002 auto-revert) not fully exercised. Agents can create arbitrary untracked files without detection.
- **Fix:** Add `git status --porcelain` or `git ls-files --others --exclude-standard` check in E002 step. Auto-delete or warn on untracked files.
- **File:** `scripts/kanban_evaluation_chain.py`

#### A8. Card 2 path prefix mismatch — agent vs plan spec
- **Evidence:** Card 1 agent created files at `scripts/smoke_utils.py`. Card 2 card body says `Files: test-plan/scripts/test_smoke_utils.py`. On run 12, E001 fired because agent wrote to `scripts/` not `test-plan/scripts/`. Worker auto-retried with `--card-body override` and succeeded on run 13.
- **Root cause:** Plan card body `Files:` line says `test-plan/scripts/` but agent's working directory resolution creates at `scripts/`. The agent interprets paths relative to the repo root, not relative to the `Files:` line's directory.
- **Impact:** One wasted agent cycle (E001 → retry). Autonomous recovery worked, but the failure was avoidable.
- **Fix:** Card 1's `Files:` line and Card 1's agent prompt must agree. The plan currently has Card 1 using `test-plan/scripts/smoke_utils.py` but the agent created at `scripts/smoke_utils.py`.
- **File:** `test-plan/kanban-standard-smoke-test.plan.md` (Card 1 body — align Files: with agent working directory)

#### A9. Token metering gap
- **Evidence:** Token log has 40 entries for this plan, but most show `tokens: {}` with `source=orchestrator`. No actual token counts from the hermes coding agent sessions.
- **Root cause:** `hermes_token_meter.py` captures delta tokens for orchestrator sessions but the coding agent (hermes binary with `-p kanban-advanced-coder`) runs in a separate profile — its token usage may not be captured by the meter running in the orchestrator context.
- **Impact:** KPI token totals only show 92 tokens (from a `cursor` source — possibly a stale prior-run entry). Actual token burn per Card 5 summary was ~215K.
- **Fix:** Token meter must capture usage from the coder profile's session, not just the orchestrator's.
- **File:** `scripts/hermes_token_meter.py`

### 🟢 LOW

#### A10. Postmortem `data_confidence: high` invalid
- **Evidence:** KPI generated at board-scoped path, but `total_tasks=17` includes `t_28871978` from another board. The confidence check `board_slug and completed == total_tasks` was true because the contamination inflated `total_tasks` past `completed`.
- **Root cause:** `generate_postmortem.py` L1568: the board-scoped data_confidence check trusts the task count from the query, but the query wasn't board-scoped.
- **Fix:** After fixing A1 (board scoping), this resolves. Add guard: if board_slug is set but any task_id isn't in that board's DB, degrade confidence.
- **File:** `scripts/generate_postmortem.py` L1568-1572

#### A11. Postmortem shows Card 5 as `running`
- **Evidence:** Postmortem Agent Performance table shows `t_53d8301f` (Card 5) as `running` when it was actually `archived` at report time.
- **Root cause:** `generate_postmortem.py` reads task status from the kanban.db snapshot but the orchestrator's card completion event may not have flushed to disk before the report ran.
- **Impact:** Cosmetic — metrics not affected (Card 5 counted as completed in totals).
- **Fix:** Re-read task status from DB right before generating the status column. Or query from `hermes kanban show` which reflects live state.
- **File:** `scripts/generate_postmortem.py`

#### A12. Fresh attestation flagged as "stale" by handoff
- **Evidence:** After regenerating attestation with `kanban_attestation.py`, running `kanban_handoff.py` failed with `git_state_not_clean: Stale state from prior run detected ... attestation: .../attestation-kanban-standard-smoke-test.yaml`.
- **Root cause:** `_check_git_freshness()` L649 checks `attestation.exists()` — existence, not timestamp. Any attestation file regardless of age triggers the guard.
- **Workaround:** Delete attestation before handoff (handoff re-runs `pre_dispatch_gate` internally which regenerates it).
- **Fix:** Check attestation file's modification time. If created within the last 5 minutes, skip. Or delete stale attestation in `git_safe_cleanup.sh`.
- **File:** `scripts/kanban_handoff.py` L649, `scripts/git_safe_cleanup.sh`

#### A13. Governance cron "config not found"
- **Evidence:** `hermes cron list` shows `[kanban-governance] ERROR: config not found` for the plan-scoped governance cron.
- **Root cause:** The governance cron runs from the repo root workdir but can't find `kanban-config.yaml` because its CWD or `KANBAN_PROJECT_ROOT` doesn't resolve correctly in the cron context.
- **Impact:** Governance checks silently skipped.
- **Fix:** Governance cron should use `--project-root` flag or set `KANBAN_PROJECT_ROOT` env var.
- **File:** `scripts/provision_kanban_crons.sh`

---

## Cross-Reference: Agent Logs vs Post-Execution Reports

### Postmortem vs Ground Truth

| Claim in Postmortem | Actual Board State | Verdict |
|-----|-----|-----|
| 17 tasks | 15 tasks (no `t_28871978`) | ❌ Cross-board contamination |
| 70.6% success | 12/15 = 80%, or 12/14 excluding gate = 85.7% | ❌ Distorted by ghost task |
| `data_confidence: high` | Cross-board contamination invalidates | ❌ False high confidence |
| Card 5 status: `running` | Card 5 status: `archived` | ❌ Stale status read |
| 2 failed/blocked | `t_61410ff5` (handoff, intentional walk-away block) + `t_e8094ab2` (transient E001 → recovered) | ⚠️ Walk-away block counted as failure |
| Intervention count: 0 | Verified: 0 manual `kanban unblock`/`kanban complete` | ✅ Correct |
| Wall clock: ~0.91h | First event 12:45, last event 13:40 = 55 min | ✅ Correct |

### KPI JSON vs Ground Truth

| Claim in KPI | Actual | Verdict |
|-----|-----|-----|
| `board_slug: null` | Board exists: `kanban-standard-smoke-test-20260630-184420` | ❌ Resolver not called |
| `token_totals.cursor: 92` | Card 5 summary says ~215K tokens | ❌ Metering gap |
| `thrash_outliers`: `t_e8094ab2` reblock_count=4 | Card 2 had 1 E001 block + 3 gate-blocks (dependency_wait) | ⚠️ Gate-blocks should be excluded per A1 fix in commit 482fc38 |
| `autonomous_pct: 100%` | All completions were autonomous (eval chain or orchestrator runbook) | ✅ Correct |
| `intervention_rate: 0.0%` | 0 interventions | ✅ Correct |

### Final Audit vs Ground Truth

| Claim | Actual | Verdict |
|-----|-----|-----|
| 9 Tier 1 violations | All are documentation-references or parser false positives | ⚠️ Many are likely false positives from backtick parsing |
| 0 Tier 2 violations | Doc coverage not exercised | ✅ Expected — smoke test plan has no doc targets |
| Exit 1 → spawned 6 remediation cards | 6 cards created, none completed | ⚠️ Remediation cards archived without completion |
| Remediation spawned for `acceptance_miss: _smoke_scratchpad.md` | The scratchpad is intentional — Card 4's acceptance says "will be auto-reverted" | ❌ False positive remediation |

---

## Execution Order (Direct)

Since this plan modifies the governance infrastructure itself, execute each fix directly — no Kanban decomposition.

### Phase 1 — Board Resolver Wiring (A1, A5, A3, A10)

**Fix A1:** Wire `generate_postmortem.py` to board resolver

```agent
agent -p "Add board resolver import to generate_postmortem.py and use it as --board fallback.
plan_id: smoke-test-20260630-findings
Files: scripts/generate_postmortem.py
Mode: modify-only
Spec:
- Import resolve_board_for_plan from lib.board_resolver
- In main(), when args.board is None, call resolved = resolve_board_for_plan(plan_id)
- Pass resolved (or args.board) as board_slug through to build_report() and build_kpi_json()
- _get_board_task_ids() already accepts board_slug — ensure it receives the resolved value
Call-sites: main() → build_report(), build_kpi_json()
Forbidden: do not change --board flag behavior when explicitly passed
Acceptance:
- Done when: generate_postmortem.py --plan-id kanban-standard-smoke-test finds only tasks on the correct board
- Verify: python3 scripts/generate_postmortem.py --plan-id kanban-standard-smoke-test --dry-run 2>&1 | grep 'Board.*184420'
Tests: python3 -c \"from lib.board_resolver import resolve_board_for_plan; assert resolve_board_for_plan('kanban-standard-smoke-test') is not None\"
Commit: fix: wire generate_postmortem.py to board resolver singleton
Diff cap: if >80 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

**Fix A5:** Stamp `board_slug` in plan memory

```agent
agent -p "Fix board_slug stamping: orchestrator must export HERMES_KANBAN_BOARD from handoff body.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_handoff.py (L884), scripts/kanban_decompose.py (L979)
Mode: modify-only
Spec:
- kanban_handoff.py L884: change 'export KANBAN_BOARD' to 'export HERMES_KANBAN_BOARD'
- kanban_decompose.py L979-981: add fallback to KANBAN_BOARD env var:
  board_slug = os.environ.get('HERMES_KANBAN_BOARD', '').strip() or os.environ.get('KANBAN_BOARD', '').strip()
Call-sites: kanban_handoff.py _build_handoff_body(), kanban_decompose.py stamp in plan memory
Forbidden: do not remove existing KANBAN_BOARD export — keep both for backward compat
Acceptance:
- Done when: plan memory JSON includes board_slug after decomposition
- Verify: grep 'HERMES_KANBAN_BOARD' scripts/kanban_handoff.py | grep -c export
Tests: python3 -c \"exec(open('scripts/kanban_handoff.py').read())\"  # syntax check only
Commit: fix: export HERMES_KANBAN_BOARD in handoff body, add KANBAN_BOARD fallback in decomposer
Diff cap: if >30 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Phase 2 — Walk-Away + Remediation Gating (A2, A3, A12)

**Fix A2:** Move walk-away gate before decomposition

```agent
agent -p "Move walk_away_mode gate BEFORE decomposition in orchestrator runbook.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_handoff.py (runbook body), plugin/data/skills/kanban-orchestrator/SKILL.md
Mode: modify-only
Spec:
- In _build_handoff_body(): move the 'Walk-away gate' section from end-of-runbook to before 'Step 2 — Create gate card'
- Change wording: 'If walk_away_mode is false, BLOCK THIS CARD NOW and do NOT proceed to decomposition'
- Add to runbook Step 1: 'CHECK walk_away_mode stamp. If false: block with reason Awaiting operator approval and STOP.'
Call-sites: _build_handoff_body() runbook generation
Forbidden: do not change walk_away_mode stamp logic — only move when the gate fires
Acceptance:
- Done when: handoff body shows walk-away gate BEFORE decomposition instructions
- Verify: python3 -c \"from scripts.kanban_handoff import _build_handoff_body; body=_build_handoff_body(...); assert 'STOP' in body and body.index('STOP') < body.index('Step 2')\"
Tests: verify handoff body ordering via dry-run: python3 scripts/kanban_handoff.py --plan test-plan/kanban-standard-smoke-test.plan.md --dry-run 2>&1 | grep -A5 'walk_away'
Commit: fix: move walk-away gate before decomposition in orchestrator runbook
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Phase 3 — Eval Chain + Agent Protocol (A4, A7)

**Fix A4:** Prevent coder sub-agent from completing cards

```agent
agent -p "Add post-agent status check to worker: detect if coding agent completed the card prematurely.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_evaluation_chain.py, scripts/coding_agent_invoke.sh
Mode: modify-only
Spec:
- In worker's agent-dispatch step (coding_agent_invoke.sh or worker skill Step 4):
  After agent returns, check 'hermes kanban show {task_id}' status
  If status is 'done' or 'completed' but eval chain hasn't run yet:
    Log warning: 'Agent completed card prematurely — running eval chain post-completion'
    Continue with eval chain (the completion happened, but we still verify)
  If eval chain DENIES: post a comment explaining the violation and revert if possible
Call-sites: coding_agent_invoke.sh _dispatch_hermes_and_meter(), worker skill Step 4
Forbidden: do not prevent legitimate agent completions — only detect and warn
Acceptance:
- Done when: worker detects premature card completion and logs warning
- Verify: grep -n 'premature' scripts/coding_agent_invoke.sh
Tests: manual smoke test — run Card 4 again and verify worker detects if agent completes prematurely
Commit: fix: detect coding agent premature card completion in worker dispatch
Diff cap: if >50 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

**Fix A7:** Add untracked file detection to E002

```agent
agent -p "Add untracked file detection to E002 eval chain step.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_evaluation_chain.py
Mode: modify-only
Spec:
- In E002_UNLISTED_FILE_CHANGE step, after git diff --name-only check:
  Run: git ls-files --others --exclude-standard
  For each untracked file that does not match allowed patterns (.agent_prompt_tmp.txt, .kanban-scope, __pycache__):
    Attempt to delete it (auto-revert)
    Log to scope_violations.jsonl with source='E002_untracked'
  If deletion fails: log violation, allow (operative), note gap
Call-sites: E002 check function in kanban_evaluation_chain.py
Forbidden: do not delete tracked files, do not break existing git diff check
Acceptance:
- Done when: untracked non-ignored files are detected and auto-deleted by E002
- Verify: create test untracked file, run eval chain, confirm deletion
Tests: python3 -c \"import subprocess; subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'])\" 
Commit: fix: add untracked file detection to E002 eval chain step
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Phase 4 — Hygiene (A6, A8, A9, A13)

**Fix A6:** Clean stale plan-scoped crons before creating new ones

```agent
agent -p "Add stale cron cleanup to provision_kanban_crons.sh --create path.
plan_id: smoke-test-20260630-findings
Files: scripts/provision_kanban_crons.sh
Mode: modify-only
Spec:
- Before creating new crons for plan_id, run 'hermes cron list' and grep for plan_id suffix
- For each matching cron that is NOT board-scoped to the current board: hermes cron remove <job_id>
- Only clean crons with matching plan_id pattern — do not touch other crons
Call-sites: provision_kanban_crons.sh --create
Forbidden: do not remove crons from other plans or the dashboard keepalive cron
Acceptance:
- Done when: second smoke test run produces only board-scoped crons, no stale plan-scoped duplicates
- Verify: hermes cron list | grep 'kanban-standard-smoke-test' | wc -l  # should be 3 (one set only)
Tests: bash scripts/provision_kanban_crons.sh --create --dry-run --board kanban-standard-smoke-test-20260630-184420
Commit: fix: clean stale plan-scoped crons before creating new ones
Diff cap: if >60 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Verification

After all fixes applied:

1. **Clean repo state:** `git status` clean, `git worktree prune`, delete stale kanban branches
2. **Push + deploy:** Push to origin → pull to installed plugin → `hermes kanban-advanced init` → restart sidecar → restart gateway
3. **Clean artifacts:** Delete old attestation, stale crons (`hermes cron remove`), old boards (`hermes kanban boards rm`)
4. **Re-run smoke test:** Full Gate 1 → Gate 2 → Gate 3 → monitor pipeline
5. **Verify fixes:**
   - A1: Postmortem shows only tasks from the correct board
   - A5: Plan memory has `board_slug`
   - A2: Walk-away gate fires before cards are created
   - A7: E002 catches and auto-deletes untracked files
   - A6: No duplicate crons after second run
