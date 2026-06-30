---
name: Smoke Test 2026-06-30 — Cross-Reference & Gap Inventory
plan_id: smoke-test-20260630-findings
line_budget: 0
overview: >
  Cross-reference of the 2026-06-30 kanban-standard-smoke-test agent logs
  against Card 5's post-execution reports (postmortem, KPI JSON, final audit).
  13 anomalies identified across 4 severity tiers, 6 research-backed patterns.
  Common thread: every kanban subsystem must use the board resolver singleton.
  Direct execution — 6 agent blocks, all call chains fully wired.
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
  note: "Fresh smoke test executed 2026-06-30 on board kanban-standard-smoke-test-20260630-184420. All 5 cards completed autonomously (0 interventions). Board resolver singleton shipped in commit 482fc38 but 3 gaps remain."
optimization_checklist:
  agent_blocks_present: pass
  no_model_in_card_bodies: pass
  iteration_budget_estimated: n/a
  files_mode_lines_present: pass
  commit_granularity_aligned: pass
  dependency_graph_drawn: skip
  card_order_finalized: skip
  line_budget_computed: n/a
  card_granularity_verified: pass
  same_file_merge_verified: n/a
  cross_section_contradictions: pass
  plan_committed: pass
  card_body_self_containment: pass
  diff_cap_present: pass
  acceptance_surface_audit: pass
  call_site_audit: pass
  verification_taxonomy: skip
  same_file_graph: pass
  multi_parent_cap: n/a
  spec_precision: pass
  markup_safe_placeholders: pass
  plan_memory_seed: skip
  platform_neutrality_acceptance: pass
  files_completeness: pass
todos:
  - id: fix-1-postmortem-resolver
    content: "Wire generate_postmortem.py to board resolver + fix data_confidence + fix stale status read"
    status: pending
  - id: fix-2-board-slug-stamp
    content: "Export HERMES_KANBAN_BOARD in handoff body; add KANBAN_BOARD fallback in decomposer L979"
    status: pending
  - id: fix-3-walkaway-gate
    content: "Move walk_away_mode gate BEFORE decomposition in orchestrator runbook + handoff body"
    status: pending
  - id: fix-4-coder-protocol
    content: "Detect premature card completion by coding agent; add post-agent status check"
    status: pending
  - id: fix-5-e002-untracked
    content: "Add git ls-files --others check to E002 for untracked file detection"
    status: pending
  - id: fix-6-cron-hygiene
    content: "Add --clean mode to provision_kanban_crons.sh + fix governance cron config + attestation freshness"
    status: pending
---
# Smoke Test 2026-06-30 — Cross-Reference & Gap Inventory

> **Execution mode:** `direct` — this plan modifies scripts under the plugin repo. Per orchestrator skill v5.5.1 § Self-referential governance, it must be executed manually, not Kanban-decomposed.

> **Board:** `kanban-standard-smoke-test-20260630-184420` | **Run:** 2026-06-30 12:45–13:40 UTC | **Interventions:** 0

> **Sanity checked:** 2026-06-30 — 7 corrections applied (line numbers, function names, paths, flags, upstream docs)

## Sanity Check Corrections

| Claim | Was | Corrected To | Why |
|-------|-----|-------------|-----|
| A12 attestation check line | L649 | L656 | L649 constructs path; `attestation.exists()` guard is at L656 |
| A10 data_confidence line | L1568 | L1571-1572 | L1568 is `token_coverage_pct`; confidence logic starts at L1571 |
| Fix A2 function name | `_build_handoff_body` | `_build_body` (L776) | Function doesn't exist; actual name verified via grep |
| Fix A2 skill path | `plugin/data/skills/` | `plugin/skills/` | Plugin bundle layout: `plugin/skills/kanban-orchestrator/SKILL.md` |
| Fix A1 verify command | `--dry-run` | resolver import check | `generate_postmortem.py` has no `--dry-run` flag |
| Fix A6 cron cleanup | assumed `--clean` exists | noted `--clean` must be added | `provision_kanban_crons.sh` only has `--create`/`--check` |
| A5 L336 awareness | not noted | noted L336 already has pattern | `kanban_decompose.py:336` already uses `or KANBAN_BOARD` fallback |
| Orchestrator skill walk-away | assumed absent | EXISTS but post-decompose | Skill says "wait for yes" but only AFTER cards dispatch |

## Common Thread

Every subsystem that queries kanban state must use `resolve_board_for_plan()` — and none self-validate their data source. The postmortem pulled `t_28871978` from board `20260630-010833` because `generate_postmortem.py` scanned all boards. `board_slug` was stamped nowhere. Three consumers shipped without the resolver (commit `482fc38`).

A secondary thread: **gating is sequenced too late**. The walk-away gate blocks the handoff card *after* decomposition — Card 5 already ran post-execution. Gate must fire before any `kanban create` call.

---

## Research Validation

Each fix cross-referenced against established best practices. Sources validated June 2026.

| Source | Pattern | Maps To |
|--------|---------|---------|
| **dev.to** — Pre-Execution Gates | Gates execute *before* side effects; policy-driven refusals | A2 (walk-away gate ordering) + A4 (coder capability gating) |
| **StackAI** — HITL Approval Workflows | "Require approval when irreversible or high blast radius" | A2 (post-exec = write action) + A3 (remediation cards gated) |
| **Azure / Hamade** — DB-per-Tenant | Hard isolation; shared-DB without tenant filter = data leak | A1 (postmortem cross-board = missing `WHERE tenant_id`) + A5 (board_slug = tenant ID) |
| **git-scm.com** — Git Porcelain | `--porcelain` stable for scripts; `ls-files --others` for untracked | A7 (E002 must check untracked files) |
| **CodeReliant** — Fail-Fast | Validate preconditions first, execute after gates pass | A2 (current gate is fail-late; fix converts to fail-fast) |
| **Azure** — Cron Isolation | Gatekeeper: isolated process validates context before acting | A3 + A6 (crons self-validate board existence before dispatch) |

---

## Anomaly Inventory

### 🔴 BLOCKING / HIGH

#### A1. Postmortem cross-board contamination
- **Evidence:** Postmortem reports 17 tasks; board has 15. `t_28871978` from board `20260630-010833`.
- **Root cause:** `generate_postmortem.py` never imported `resolve_board_for_plan()`. Falls back to scanning ALL boards.
- **Impact:** Success rate distorted (70.6% vs true 80%), KPI `data_confidence: high` is false, task list includes ghosts.
- **Fix:** Wire resolver into `generate_postmortem.py` main(); also fix A10 (data_confidence guard) and A11 (stale status read) in same file.
- **File:** `scripts/generate_postmortem.py`

#### A2. Walk-away gate defeated — post-execution ran autonomously
- **Evidence:** Handoff stamps `walk_away_mode: false`. Orchestrator decomposed → dispatched 5 cards → Card 5 ran final audit + postmortem → *then* blocked for approval.
- **Root cause:** Runbook sequences decomposition BEFORE walk-away check. Card 5 `Acceptance:` is unconditional.
- **Impact:** Operator loses control of post-execution. Unverified artifacts produced without approval.
- **Fix:** Move walk-away gate in `_build_body()` to BEFORE Step 2. If false, block card immediately — no decomposition.
- **Files:** `scripts/kanban_handoff.py` (_build_body), `plugin/skills/kanban-orchestrator/SKILL.md`

#### A3. Remediation cards archived without autonomous completion
- **Evidence:** 6 remediation cards spawned, all `archived` with no `completed` events.
- **Root cause:** Auto_unblock cron uses board-scoped scripts in card5 worktree; gateway cron store isolation prevents card visibility.
- **Impact:** Remediation loop exercised but not effective. Layer 2 recovery not proven.
- **Fix:** Verified in A6 (cron cleanup) and A5 (board_slug stamping). Crons must self-validate board context before acting.
- **Files:** `scripts/provision_kanban_crons.sh`, `scripts/kanban_handoff.py`

#### A4. Coder sub-agent protocol violation on Card 4
- **Evidence:** Coding agent called `kanban_complete` directly. Eval chain found E003 failure but card already marked `done`.
- **Root cause:** Agent bypassed worker. No post-agent status check existed.
- **Impact:** Eval chain enforcement bypassed.
- **Fix:** Add post-dispatch status check in `coding_agent_invoke.sh`. If card completed prematurely, log warning and re-run eval chain.
- **Files:** `scripts/coding_agent_invoke.sh`, `scripts/kanban_evaluation_chain.py`

### 🟡 DEGRADED

#### A5. `board_slug` not stamped in plan memory
- **Evidence:** `.hermes/kanban/memory/kanban-standard-smoke-test.json` has no `board_slug` key.
- **Root cause:** Handoff body exports `KANBAN_BOARD` but decomposer L979 only checks `HERMES_KANBAN_BOARD`. Env var not inherited across gateway session boundary.
- **Fix:** Change handoff body L884 to `export HERMES_KANBAN_BOARD`. Decomposer L979: add `or os.environ.get("KANBAN_BOARD")` fallback (L336 already has this pattern).
- **Files:** `scripts/kanban_handoff.py` L884, `scripts/kanban_decompose.py` L979

#### A6. Duplicate crons (board-scoped + plan-scoped)
- **Evidence:** Both `kanban-auto-unblock-1m` (board-scoped) and `kanban-auto-unblock-1m-kanban-standard-smoke-test` (plan-scoped) coexist.
- **Root cause:** `provision_kanban_crons.sh` creates new crons each handoff; never cleans stale ones.
- **Fix:** Add `--clean` mode to remove stale plan-scoped crons before creating new ones.
- **File:** `scripts/provision_kanban_crons.sh`

#### A7. E002 gap: untracked files not detected
- **Evidence:** Card 4 created `_smoke_scratchpad.md` as untracked. E002 only checks `git diff --name-only`.
- **Root cause:** `kanban_evaluation_chain.py` E002 step lacks `git ls-files --others --exclude-standard`.
- **Impact:** Layer 1 autonomous recovery not fully exercised.
- **Fix:** Add untracked file check + auto-delete in E002 step.
- **File:** `scripts/kanban_evaluation_chain.py`

#### A8. Card 2 path prefix mismatch — agent vs plan spec
- **Evidence:** Agent created at `scripts/` but plan says `test-plan/scripts/`. E001 fired on run 12; worker auto-recovered on run 13.
- **Root cause:** Plan `Files:` line and agent working directory disagree.
- **Fix:** Update `test-plan/kanban-standard-smoke-test.plan.md` Card 1 body to align `Files:` with agent's actual working directory. (Plan-level fix, no code change.)
- **File:** `test-plan/kanban-standard-smoke-test.plan.md`

#### A9. Token metering gap
- **Evidence:** 40 token log entries; most have `tokens: {}` with `source=orchestrator`. Actual burn ~215K.
- **Root cause:** `hermes_token_meter.py` captures orchestrator session deltas, not coder profile session.
- **Impact:** KPI token totals useless (92 tokens reported vs ~215K actual).
- **Fix:** `hermes_token_meter.py` must capture from coder profile's `tokens.jsonl` as well. Merge coder-profile entries matching plan's task_ids.
- **File:** `scripts/hermes_token_meter.py`

### 🟢 LOW

#### A10. Postmortem `data_confidence: high` invalid
- **Evidence:** Confidence set to `high` despite cross-board contamination inflating `total_tasks`.
- **Fix:** Resolves with A1. Add guard: if board_slug and any task_id not in that board's DB, degrade confidence.
- **File:** `scripts/generate_postmortem.py` L1571-1572

#### A11. Postmortem shows Card 5 as `running`
- **Evidence:** Status read from stale DB snapshot.
- **Fix:** Re-read status from `hermes kanban show` right before generating status column.
- **File:** `scripts/generate_postmortem.py`

#### A12. Fresh attestation flagged as "stale" by handoff
- **Evidence:** `_check_git_freshness()` L656 checks `attestation.exists()` — existence, not timestamp.
- **Fix:** At L656, check modification time. If created within last 5 minutes, skip.
- **File:** `scripts/kanban_handoff.py` L656

#### A13. Governance cron "config not found"
- **Evidence:** `[kanban-governance] ERROR: config not found` in cron list.
- **Fix:** Governance cron needs `--project-root` flag or `KANBAN_PROJECT_ROOT` env var set.
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
| 2 failed/blocked | Handoff (intentional walk-away) + Card 2 (transient E001 → recovered) | ⚠️ Walk-away block counted as failure |
| Intervention count: 0 | Verified: 0 manual `kanban unblock`/`kanban complete` | ✅ Correct |
| Wall clock: ~0.91h | First event 12:45, last 13:40 = 55 min | ✅ Correct |

### KPI JSON vs Ground Truth

| Claim in KPI | Actual | Verdict |
|-----|-----|-----|
| `board_slug: null` | Board exists: `kanban-standard-smoke-test-20260630-184420` | ❌ Resolver not called |
| `token_totals.cursor: 92` | Card 5 summary says ~215K tokens | ❌ Metering gap |
| `thrash_outliers`: `t_e8094ab2` reblock_count=4 | 1 E001 + 3 gate-blocks | ⚠️ Gate-blocks should be excluded |
| `autonomous_pct: 100%` | All completions autonomous | ✅ Correct |
| `intervention_rate: 0.0%` | 0 interventions | ✅ Correct |

---

## Execution Order (Direct)

Six agent blocks, wired with complete downstream call chains. Execute in order — each fix may affect the next.

### Block 1 — Postmortem Board Scoping (A1, A10, A11)

```agent
agent -p "Wire generate_postmortem.py to board resolver singleton and fix data_confidence + stale status.
plan_id: smoke-test-20260630-findings
Files: scripts/generate_postmortem.py
Mode: modify-only
Spec:
- Import resolve_board_for_plan from lib.board_resolver (top of file, near other lib imports)
- In main(): when args.board is None, call resolved = resolve_board_for_plan(plan_id) and store
- Thread board_slug through to build_report() and build_kpi_json() (already accept board_slug kwarg)
- _get_board_task_ids() already accepts board_slug — verify it receives the resolved value
- At L1571-1572: add guard after data_confidence='high' assignment: if board_slug set but any task_id not in board's kanban.db, degrade to 'medium'
- For stale status (A11): in the agent performance table loop, re-read status from hermes kanban show <tid> instead of cached task.status attribute
Call-sites:
- main() L~2029: argparse --board → resolve_board_for_plan fallback
- build_report() L~920: receives board_slug → passes to _get_board_task_ids()
- build_kpi_json() L~1550: receives board_slug → used for data_confidence
- _get_board_task_ids() L~1926: runs hermes kanban --board <slug> list --json
Downstream dependents (no change needed, but verify):
- kanban_token_report.py L194-195: already uses resolve_board_for_plan()
- kanban_lifecycle_notify.sh L94-98: already uses resolve_board_for_plan()
- final_audit_sanity.py L74-75: already uses resolve_board_for_plan()
Forbidden: do not change --board flag behavior when explicitly passed
Acceptance:
- Done when: generate_postmortem.py --plan-id kanban-standard-smoke-test produces only tasks from board 20260630-184420
- Verify: python3 -c "from lib.board_resolver import resolve_board_for_plan; r = resolve_board_for_plan('kanban-standard-smoke-test'); assert r and '184420' in r; print(r)"
Tests: python3 -m pytest tests/test_board_resolver.py -q
Commit: fix: wire generate_postmortem.py to board resolver singleton, fix data_confidence guard, fix stale status read
Diff cap: if >120 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Block 2 — Board Slug Stamping (A5)

```agent
agent -p "Fix board_slug stamping: export HERMES_KANBAN_BOARD in handoff body, add KANBAN_BOARD fallback in decomposer.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_handoff.py, scripts/kanban_decompose.py
Mode: modify-only
Spec:
- kanban_handoff.py L884: change 'export KANBAN_BOARD=\"{kanban_board}\"' to 'export HERMES_KANBAN_BOARD=\"{kanban_board}\"'
  (Keep KANBAN_BOARD export too for backward compat — add a second export line)
- kanban_decompose.py L979: change from:
    board_slug = os.environ.get(\"HERMES_KANBAN_BOARD\", \"\").strip()
    to:
    board_slug = os.environ.get(\"HERMES_KANBAN_BOARD\", \"\").strip() or os.environ.get(\"KANBAN_BOARD\", \"\").strip()
  (Same pattern already used at L336 for a different code path)
Call-sites:
- kanban_handoff.py _build_body() L776 → L884: generates handoff body text exported by orchestrator
- kanban_decompose.py L979-981: stamps board_slug into plan memory JSON during decomposition
Downstream dependents:
- board_resolver.py L48: reads HERMES_KANBAN_BOARD (Priority 1) — now satisfied
- generate_postmortem.py (after Block 1): uses resolve_board_for_plan() which checks HERMES_KANBAN_BOARD
- kanban_lifecycle_notify.sh L90-98: uses resolve_board_for_plan()
- final_audit_sanity.py L74-75: uses resolve_board_for_plan()
Forbidden: do not remove existing KANBAN_BOARD export — add HERMES_KANBAN_BOARD alongside it
Acceptance:
- Done when: plan memory JSON includes board_slug key after next decomposition
- Verify: grep 'HERMES_KANBAN_BOARD' scripts/kanban_handoff.py | grep 'export'
Tests: python3 -c \"exec(open('scripts/kanban_handoff.py').read())\"  # syntax check
Commit: fix: export HERMES_KANBAN_BOARD in handoff body, add KANBAN_BOARD fallback in decomposer
Diff cap: if >20 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Block 3 — Walk-Away Gate Ordering (A2, A12)

```agent
agent -p "Move walk_away_mode gate BEFORE decomposition in orchestrator runbook and fix attestation freshness check.
plan_id: smoke-test-20260630-findings
Files: scripts/kanban_handoff.py, plugin/skills/kanban-orchestrator/SKILL.md
Mode: modify-only
Spec:
- In _build_body() L776: the Walk-away gate section currently appears near end of runbook (after Step 4).
  Move it to between Step 1 (gate check) and Step 2 (create gate card).
  Current order: Gate check → Decompose → Dispatch → Monitor → Walk-away gate
  New order: Gate check → Walk-away gate → [if approved] Decompose → Dispatch → Monitor
- Change wording from 'STOP — Operator approval required before Step 5' to 'STOP — Operator approval required before Step 2. If walk_away_mode is false, BLOCK THIS CARD NOW with reason \"Awaiting operator approval for decomposition.\" Do NOT create any cards.'
- Update runbook Step 1: add instruction to check walk_away_mode stamp before gate card creation
- In orchestrator SKILL.md: add post-card-completion checkpoint: when all implementation cards done and walk_away_mode false, block root card — do not create final audit card until unblocked
- Fix A12: at L656, change 'if attestation.exists():' to check st_mtime < (now - 300) before flagging as stale:
    if attestation.exists():
        age = time.time() - attestation.stat().st_mtime
        if age > 300: issues.append(...)
Call-sites:
- _build_body() L776: generates handoff card body — walk-away gate text
- orchestrator SKILL.md § Step 2b: orchestrator reads and follows runbook
Downstream dependents:
- kanban_decompose.py: receives handoff card as ready → reads walk_away_mode stamp → must honor the block
- Card 5 verification worker: must check walk_away_mode before running post-execution steps
Forbidden: do not change walk_away_mode stamp logic — only move when the gate fires
Acceptance:
- Done when: dry-run handoff body shows walk-away gate BEFORE decomposition instructions
- Verify: python3 scripts/kanban_handoff.py --plan test-plan/kanban-standard-smoke-test.plan.md --dry-run 2>&1 | grep -A5 'walk_away'
Tests: verify handoff body text order: python3 -c \"from scripts.kanban_handoff import _build_body; print('import OK')\"
Commit: fix: move walk-away gate before decomposition, add attestation freshness check
Diff cap: if >60 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Block 4 — Coder Protocol + E002 Untracked (A4, A7)

```agent
agent -p "Add post-agent status check for premature card completion, and add untracked file detection to E002.
plan_id: smoke-test-20260630-findings
Files: scripts/coding_agent_invoke.sh, scripts/kanban_evaluation_chain.py
Mode: modify-only
Spec:
A4 — Coder protocol violation detection:
- In _dispatch_hermes_and_meter() (coding_agent_invoke.sh): after agent returns and output is captured,
  before running eval chain, check card status:
  status=$(hermes kanban show \"$TASK_ID\" 2>/dev/null | grep '^  status:' | awk '{print $2}')
  if [ \"$status\" = \"done\" ] || [ \"$status\" = \"completed\" ]; then
    echo \"[WARN] Agent completed card $TASK_ID prematurely — re-running eval chain post-completion\"
  fi
- Document in worker skill Step 4: \"After agent returns, check card status. If done prematurely, log and continue eval chain.\"
A7 — E002 untracked file detection:
- In E002_UNLISTED_FILE_CHANGE step (kanban_evaluation_chain.py), after existing git diff --name-only check:
  Run: git ls-files --others --exclude-standard
  For each untracked file NOT matching allowed patterns (.agent_prompt_tmp.txt, .kanban-scope, __pycache__, *.pyc):
    Attempt os.remove(filepath)
    If successful: log to scope_violations.jsonl with source='E002_untracked', action='auto_deleted'
    If deletion fails: log violation with action='delete_failed', set ALLOW status with note
  Allowed patterns are worker artifacts — everything else is a potential scope violation
Call-sites:
- coding_agent_invoke.sh: _dispatch_hermes_and_meter() → post-dispatch status check
- kanban_evaluation_chain.py: E002_UNLISTED_FILE_CHANGE → + untracked check
Downstream dependents:
- kanban_evaluation_chain.py: E003 (test pass) depends on E002 passing first
- generate_postmortem.py: reads scope_violations.jsonl for postmortem §2
- scope_violations.jsonl: board-scoped via _scope_violations_path(board_slug) — already wired
Forbidden: do not delete tracked files, do not break existing git diff check
Acceptance:
- Done when: worker detects premature completion AND E002 catches + deletes untracked files
- Verify A4: grep -n 'premature' scripts/coding_agent_invoke.sh
- Verify A7: python3 -c \"import subprocess; subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'])\"
Tests: manual smoke — run Card 4 again, verify worker detects agent completion + E002 auto-deletes scratchpad
Commit: fix: detect premature card completion, add untracked file detection to E002
Diff cap: if >80 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Block 5 — Cron Hygiene (A6, A13)

```agent
agent -p "Add --clean mode to provision_kanban_crons.sh and fix governance cron config resolution.
plan_id: smoke-test-20260630-findings
Files: scripts/provision_kanban_crons.sh
Mode: modify-only
Spec:
A6 — Stale cron cleanup:
- Add new --clean mode to provision_kanban_crons.sh (currently only --create and --check exist)
- --clean: for each crons prefix (kanban-auto-unblock-1m, kanban-board-keeper-3m, kanban-lifecycle-notify-5m, kanban-governance):
    List all matching cron jobs via 'hermes cron list'
    For each job whose name contains the plan_id suffix but whose workdir does NOT contain the current board slug:
      hermes cron remove <job_id>
    For each job whose name does NOT contain the plan_id suffix: skip (leave alone)
- In --create mode: call --clean first for the same plan_id, then create new crons
A13 — Governance cron config:
- When creating governance cron, add explicit --project-root flag:
  hermes cron create ... --workdir \"$REPO_ROOT\" --script provision_kanban_crons.sh --project-root \"$REPO_ROOT\"
- Or: set KANBAN_PROJECT_ROOT env var in the cron script body
  export KANBAN_PROJECT_ROOT=\"$REPO_ROOT\"
- Verify governance cron shows no 'config not found' error after fix
Call-sites:
- provision_kanban_crons.sh --create → calls internal _clean_stale_crons() first
- kanban_handoff.py L1142-1164: calls provision_kanban_crons.sh with --create flag
Downstream dependents:
- kanban_handoff.py: cron provisioning during handoff
- Gateway cron store: receives cleaned crons without duplicates
- kanban_lifecycle_notify.sh, board_keeper.sh: board-scoped crons that depend on correct context
Forbidden: do not remove kanban-dashboard-keepalive cron or crons from other plans
Acceptance:
- Done when: second smoke test run produces only 3 board-scoped crons (auto-unblock, board-keeper, lifecycle-notify), no stale plan-scoped duplicates
- Verify: hermes cron list | grep 'kanban-standard-smoke-test' | wc -l  # should be 3
Tests: bash scripts/provision_kanban_crons.sh --create --board kanban-standard-smoke-test-20260630-184420 --dry-run 2>&1
Commit: fix: add --clean mode to provision_kanban_crons.sh, fix governance cron config
Diff cap: if >80 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

### Block 6 — Token Metering + Plan Hygiene (A8, A9)

```agent
agent -p "Fix token metering to capture coder profile usage, and align smoke test plan Card 1 Files: with agent working directory.
plan_id: smoke-test-20260630-findings
Files: scripts/hermes_token_meter.py, test-plan/kanban-standard-smoke-test.plan.md
Mode: modify-only
Spec:
A9 — Token metering cross-profile capture:
- In hermes_token_meter.py: after capturing orchestrator session delta tokens,
  also scan coder profile's tokens.jsonl ($HERMES_HOME/profiles/kanban-advanced-coder/kanban/tokens.jsonl)
  For each entry matching the current plan's task_ids: merge token counts
  Sum tokens across profiles into total_tokens dict
  If coder profile tokens.jsonl not found: log warning, use orchestrator-only totals
- Ensure token source field distinguishes: source='orchestrator' vs source='coder_profile'
A8 — Plan alignment:
- In test-plan/kanban-standard-smoke-test.plan.md Card 1 body:
  The Files: line says 'test-plan/scripts/smoke_utils.py' but agent creates at 'scripts/smoke_utils.py'
  Change Card 1 Files: to 'scripts/smoke_utils.py' (repo root) to match agent's working directory
  Or: add explicit instruction in Card 1 Spec: 'Create at scripts/smoke_utils.py (repo root, not test-plan/scripts/)'
  Also update Card 2-4 Files: lines to consistently use 'scripts/' prefix
Call-sites:
- hermes_token_meter.py: invoked by coding_agent_invoke.sh after agent dispatch
- kanban-standard-smoke-test.plan.md: read by kanban_decompose.py during decomposition
Downstream dependents:
- generate_postmortem.py: reads tokens.jsonl for token economics section
- build_kpi_json(): includes token_totals in KPI JSON
- Card 2: depends on Card 1's output file location
Forbidden: do not break orchestrator-only token capture; plan Files: changes must not break V008 validation
Acceptance:
- Done when: KPI token_totals show realistic counts (~200K+) and Card 1 agent creates file at correct path
- Verify A9: python3 -c \"from scripts.hermes_token_meter import *; print('import OK')\"
- Verify A8: grep 'Files:.*smoke_utils' test-plan/kanban-standard-smoke-test.plan.md
Tests: manual — run smoke test and verify KPI token_totals are not 92
Commit: fix: capture coder profile tokens in meter, align smoke test plan Files: paths
Diff cap: if >60 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Downstream Wiring Map

```
Block 1 (postmortem resolver)
  ├─→ generate_postmortem.py: main(), build_report(), build_kpi_json(), _get_board_task_ids()
  ├─→ kanban_token_report.py L194 (already wired — verify)
  ├─→ kanban_lifecycle_notify.sh L94 (already wired — verify)
  └─→ final_audit_sanity.py L74 (already wired — verify)

Block 2 (board_slug stamp)
  ├─→ kanban_handoff.py L884: export HERMES_KANBAN_BOARD
  ├─→ kanban_decompose.py L979: add KANBAN_BOARD fallback
  ├─→ board_resolver.py L48: reads HERMES_KANBAN_BOARD (Priority 1)
  └─→ all consumers in Block 1's downstream tree

Block 3 (walk-away gate)
  ├─→ kanban_handoff.py _build_body() L776: gate text reordering
  ├─→ plugin/skills/kanban-orchestrator/SKILL.md: runbook checkpoint
  ├─→ kanban_decompose.py: must honor blocked handoff card
  └─→ Card 5 verification worker: must check walk_away_mode

Block 4 (coder protocol + E002)
  ├─→ coding_agent_invoke.sh: _dispatch_hermes_and_meter()
  ├─→ kanban_evaluation_chain.py: E002_UNLISTED_FILE_CHANGE
  ├─→ scope_violations.jsonl: board-scoped logging
  └─→ generate_postmortem.py: reads scope_violations.jsonl

Block 5 (cron hygiene)
  ├─→ provision_kanban_crons.sh: --clean mode + governance config
  ├─→ kanban_handoff.py: cron provisioning during handoff
  └─→ gateway cron store: receives cleaned crons

Block 6 (token metering + plan hygiene)
  ├─→ hermes_token_meter.py: cross-profile token capture
  ├─→ kanban-standard-smoke-test.plan.md: Files: alignment
  ├─→ generate_postmortem.py: reads tokens.jsonl
  └─→ build_kpi_json(): includes token_totals
```

---

## Verification

After all blocks applied:

1. **Clean repo state:** `git status` clean, `git worktree prune`, delete stale kanban branches
2. **Push + deploy:** Push to origin → pull to installed plugin → `hermes kanban-advanced init` → restart sidecar → restart gateway
3. **Clean artifacts:** Delete old attestation, stale crons, old boards
4. **Re-run smoke test:** Full Gate 1 → Gate 2 → Gate 3 → monitor pipeline
5. **Verify fixes:**
   - A1: Postmortem shows only tasks from correct board
   - A5: Plan memory has `board_slug`
   - A2: Walk-away gate fires before cards created
   - A7: E002 catches + deletes untracked files
   - A6: No duplicate crons
   - A9: KPI token_totals show realistic counts
