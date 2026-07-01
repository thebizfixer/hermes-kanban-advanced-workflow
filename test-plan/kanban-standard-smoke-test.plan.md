---
name: Kanban Standard Smoke Test
plan_id: kanban-standard-smoke-test
line_budget: 145
overview: >
  End-to-end autonomous-operation validation for the kanban-advanced plugin
  on vanilla Hermes Agent kanban.  Verifies: handoff → preflight gate →
  decompose → dispatch → worker execution → eval-chain governance (E001–E023)
  → TWO-LAYER autonomous error recovery (Card 4: E002 auto-revert at the
  worker level; Card 5 + final-audit: remediation-card loop at the
  orchestrator level) → postmortem generation.  The smoke test PASSES when
  all five cards complete (or Card 4 blocks on E002) with zero manual
  intervention and a postmortem is produced.  It FAILS if any card requires
  manual unblock, manual completion, or human triage — signalling the plugin
  needs hardening before it can run unattended.
isProject: false
optimization_checklist:
  agent_blocks_present: pass
  no_model_in_card_bodies: pass
  iteration_budget_estimated: pass
  files_mode_lines_present: pass
  commit_granularity_aligned: pass
  dependency_graph_drawn: pass
  card_order_finalized: pass
  line_budget_computed: pass
  card_granularity_verified: pass
  same_file_merge_verified: pass
  cross_section_contradictions: pass
  plan_committed: pass
  card_body_self_containment: pass
  diff_cap_present: pass
  acceptance_surface_audit: pass
  call_site_audit: pass
  verification_taxonomy: pass
  same_file_graph: pass
  multi_parent_cap: pass
  spec_precision: pass
  markup_safe_placeholders: pass
  plan_memory_seed: pass
  platform_neutrality_acceptance: pass
  files_completeness: pass
prior_run_learnings:
  note: "Fresh smoke test aligned with orchestrator v5.5.1 / planning v5.5.0 / hermes v0.17.0. Prior runs exercised basic dispatch but lacked autonomous-recovery coverage (final-audit remediation loop) and used a manual agent-block preflight instead of preflight.sh + pre_dispatch_gate.sh."
contingencies:
  - risk: "Coding agent not configured (KANBAN_CODING_AGENT unset or binary missing)"
    probability: High
    impact: BLOCKING
    mitigation: "Run `hermes kanban-advanced init` and set `coding_agent_binary` in kanban-config.yaml. See `plugin/data/references/coding-agent-auth.md`."
    auto_retry: false
  - risk: "Coding agent auth failure (OAuth expired / API key missing)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Authenticate coding CLI per `plugin/data/references/coding-agent-auth.md`. Re-run pre_dispatch_gate.sh after auth fix."
    auto_retry: false
  - risk: "Gateway not running (dispatcher won't claim cards)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Start gateway: `hermes gateway run`. Verify: `hermes kanban list` shows cards. The pre_dispatch_gate.sh warns on this."
    auto_retry: false
  - risk: "E002 unlisted file auto-revert fails → card blocks (acceptable — governance gate is working; Card 4 validates either outcome)"
    probability: Expected
    impact: DEGRADED
    mitigation: "Archive the blocked Card 4. The E002 gate is proven operational. Card 5 still runs and the smoke test still passes."
    auto_retry: false
  - risk: "Final audit spawns remediation cards that also fail → manual intervention needed → smoke test FAILS"
    probability: Low
    impact: BLOCKING
    mitigation: "Investigate why remediation workers can't fix the audit violation. This is a plugin bug — harden before re-running."
    auto_retry: false
  - risk: "Subagent gate interrupted (parallel subagents crash mid-exec on Windows)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Fall back to serial gate: set `subagent_gate.enabled: false` in kanban-config.yaml, then run `bash scripts/pre_dispatch_gate.sh kanban-standard-smoke-test` directly."
    auto_retry: false
  - risk: "validate_card_bodies V008 false-positive on create-only files"
    probability: Low
    impact: BLOCKING
    mitigation: "card_body_fidelity.py L258-260 already skips create-only files. If you encounter V008, update the plugin (this was fixed post-v0.17.0)."
    auto_retry: false
  - risk: "Token metering fallback to estimated tier (reduces KPI accuracy but doesn't block execution)"
    probability: Medium
    impact: DEGRADED
    mitigation: "Accept estimated tokens in postmortem. Audit the metering pipeline after the smoke test."
    auto_retry: false
todos:
  - id: card-1-utils
    content: "Create test-plan/scripts/smoke_utils.py with greet(), add(), format_name()"
    status: pending
  - id: card-2-tests
    content: "Create test-plan/scripts/test_smoke_utils.py with pytest tests for all three functions"
    status: pending
  - id: card-3-modify
    content: "Modify test-plan/scripts/smoke_utils.py to add multiply() + update tests (modify-only + cross-file rebase)"
    status: pending
  - id: card-4-e002-recovery
    content: "Autonomous recovery test: agent adds docstring + creates unlisted scratchpad → E002 auto-revert recovers → card completes"
    status: pending
  - id: card-5-verify
    content: "Verification: run test suite, final_audit_sanity.py with remediation loop, token report, postmortem"
    status: pending
acceptance_matrix:
  card1:
    - "test-plan/scripts/smoke_utils.py exists with greet(), add(), format_name()"
    - "assert greet() == 'hello from kanban'"
    - "assert add(2,3) == 5"
    - "assert format_name('Jane','Doe') == 'Doe, Jane'"
  card2:
    - "pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests"
    - "test_add_positive, test_add_negative, test_add_zero pass"
    - "test_format_name_standard, test_format_name_single pass"
  card3:
    - "multiply(3,4) == 12"
    - "pytest passes all tests including test_multiply_positive and test_multiply_zero"
    - "Existing greet/add/format_name unchanged"
  card4:
    - "Module docstring present on smoke_utils.py"
    - "E002_UNLISTED_FILE_CHANGE triggered for _smoke_scratchpad.md"
    - "Unlisted file auto-reverted (card completes) OR card blocks on E002 — both are PASS outcomes"
  card5:
    - "Full test suite passes: pytest test-plan/scripts/test_smoke_utils.py -v"
    - "final_audit_sanity.py --tier all exit 0 (possibly after remediation)"
    - "Token report runs: python3 scripts/kanban_token_report.py --plan kanban-standard-smoke-test"
    - "Postmortem generated: .hermes/kanban/reports/kanban-standard-smoke-test_postmortem_*.md"
    - "KPI artifacts exist: .hermes/kanban/reports/kanban-standard-smoke-test_kpi.json"
---

# Kanban Standard Smoke Test

> **Purpose:** Validate a kanban-advanced installation end-to-end on vanilla Hermes Agent kanban. Exercises the full autonomous pipeline — handoff, preflight gate, decomposition, dispatch, worker execution, eval-chain governance, autonomous error recovery (E002 auto-revert + final-audit remediation loop), and postmortem generation. The smoke test PASSES when every stage completes without manual intervention.

<!-- skip-validate V001 -- Prerequisites: documentation references only, no work targets -->
> **Prerequisites:**
> - Hermes Agent ≥ 0.17.0
> - `hermes kanban-advanced init` completed successfully **in the target repository** (the repo you want to smoke-test)
> - Coding agent binary configured in `.hermes/kanban-overrides/kanban-config.yaml` (`coding_agent_binary`)
> - Coding agent authenticated (see `plugin/data/references/coding-agent-auth.md`)
> - Gateway running (`hermes gateway run` or scheduled task)
> - `auto_decompose: false` in Hermes kanban config (`hermes config set kanban.auto_decompose false`)
> - **Working directory: the target repository root** (not the plugin clone)
> - This plan file copied to `.hermes/kanban/plans/kanban-standard-smoke-test.plan.md` in the target repo
> - `test-plan` present in `plan_search_dirs` overlay config (default; ensures scripts find the plan)

> **Expected duration:** 20–40 minutes (depends on coding agent speed + remediation wave)
> **Expected outcome:** 4 code-gen cards dispatched, 3 completed (Cards 1–3), 1 completed-or-blocked (Card 4 — E002 autonomous recovery), 1 verification card passed (Card 5 — including optional remediation wave). Zero manual interventions. Postmortem + KPI JSON generated. The smoke test validates both recovery layers: Layer 1 (E002 auto-revert) always exercised; Layer 2 (remediation cards) exercised if any latent issues exist, or via the force-trigger documented in Card 5.
<!-- /skip-validate -->

---

<!-- skip-validate V001 -- Success Criteria: documentation references only, no work targets -->
## Success Criteria

The smoke test **PASSES** when ALL of the following are true:

- [ ] Preflight (`preflight.sh`) exits with `pass` or `degraded` (no blocking failures)
- [ ] Pre-dispatch gate (`pre_dispatch_gate.sh`) exits 0
- [ ] Handoff card created by `kanban_handoff.py` → orchestrator decomposes → all 5 cards dispatched
- [ ] Card 1 completed: `test-plan/scripts/smoke_utils.py` exists with `greet()`, `add()`, `format_name()`
- [ ] Card 2 completed: `test-plan/scripts/test_smoke_utils.py` exists, pytest passes 6 tests
- [ ] Card 3 completed: `multiply()` added, tests updated and pass
- [ ] Card 4 completed (E002 auto-revert succeeded — autonomous recovery Layer 1) OR blocked (E002 revert failed — governance gate operational, also autonomous)
- [ ] Card 5 completed: test suite passes, final audit passes (exit 0, possibly after remediation — autonomous recovery Layer 2)
- [ ] **Zero manual interventions** — no `hermes kanban unblock`, no `hermes kanban complete` by human, no manual triage of any blocked card
- [ ] Postmortem generated at `.hermes/kanban/reports/kanban-standard-smoke-test_postmortem_*.md`
- [ ] KPI JSON generated at `.hermes/kanban/reports/kanban-standard-smoke-test_kpi.json`
- [ ] Token log (`tokens.jsonl`) has entries for all completed cards + orchestrator checkpoints

The smoke test **FAILS** when ANY of the following occur:
- [ ] Any card stuck in `blocked` > 10 minutes without autonomous recovery (E023 escalation, board-keeper salvage, or final-audit remediation)
- [ ] Any card requires manual `kanban unblock` or `kanban complete` by a human
- [ ] Gateway notification pages the operator for a non-recoverable failure
- [ ] Postmortem not generated within 15 minutes of final card completion
- [ ] `final_audit_sanity.py --tier all` loop exceeds max remediation rounds without reaching exit 0 (remediation loop couldn't self-heal — **plugin gap**)

**When the smoke test fails:** Stop the kanban. Do NOT hand-fix cards. Investigate the plugin gap that required manual intervention, harden the plugin, and re-run. The goal is unattended operation — every manual intervention is a bug to fix.

<!-- /skip-validate -->

---

<!-- skip-validate V001 -- Architecture Notes: documentation references only, no work targets -->
## Architecture Notes

### Execution Pipeline (current plugin)

```
Operator (default profile)
  │
  ├─ 1. bash "$HERMES_HOME/scripts/preflight.sh"      ← env gating (13+ checks)
  ├─ 2. bash "$HERMES_HOME/scripts/pre_dispatch_gate.sh" {id}  ← plan + CLI + attestation
  └─ 3. python3 "$HERMES_HOME/scripts/kanban_handoff.py"      ← handoff card + cron provision
         --plan .hermes/kanban/plans/{plan_id}.plan.md
              │
              ▼
Orchestrator (orchestrator profile)
  │
  ├─ Receives handoff card → decomposes via runbook
  ├─ validate_board.sh → completes gate → dispatches Cards 1-5
  ├─ Monitors workers (watch / cron)
  └─ When Card 5 done → final_audit_sanity.py --tier all
       │
       ├─ exit 0 → postmortem → cleanup
       └─ exit 1 → --spawn-remediation → remediation wave → re-audit → exit 0
```

> **Scripts are materialized** to `$HERMES_HOME/scripts/` by `hermes kanban-advanced init`. They run from any repo — no plugin clone needed. The plan file lives in the **target repo** (`.hermes/kanban/plans/` or `test-plan/`). Generated artifacts (`smoke_utils.py`, tests, postmortems) are created in the target repo's `test-plan/` directory.

### Autonomous Recovery Mechanisms Tested

| Layer | Mechanism | Trigger | Tested By | Type |
|-------|-----------|---------|-----------|------|
| **Worker (eval chain)** | E002 auto-revert | Agent creates unlisted file → auto-revert or block | Card 4 | Automatic (in-chain) |
| **Worker (eval chain)** | E023 lattice memory | Repeated identical error → escalate | (passive — prevents loops) | Automatic (in-chain) |
| **Orchestrator (final audit)** | Remediation cards | `final_audit_sanity.py` exit 1 → `--spawn-remediation` → workers fix → re-audit | Card 5 + force-trigger | Automatic (separate cards, `Type: remediation`) |
| **Orchestrator (board keeper)** | Salvage pattern | Iteration budget exhausted, work present → fetch + merge | (passive — cron-based) | Automatic (direct action) |
| **Orchestrator (cron)** | Auto-unblock | Parent completed → promote child | Cards 2-5 (wave progression) | Automatic (cron-based) |

### Token Logging

The kanban-advanced plugin supports three tiers of token metering:

| Tier | Source | Agents | Mechanism |
|------|--------|--------|-----------|
| 1 | `agent` | Cursor, Claude Code, Codex, Gemini, Grok | Exact from agent JSON `usage` block |
| 2 | `hermes_insights` | hermes | Authoritative — Hermes insights delta (provider response headers) |
| 3 | `estimated` | aider, unknown binaries | Character-count estimation |

**Orchestrator checkpoints (logged by `hermes_token_meter.py`):** planning-complete, decompose-complete, audit-start, cleanup-complete.

<!-- /skip-validate -->

---

<!-- skip-validate V001 -- Gate Hardening: documentation references only, no work targets -->
## Gate Hardening

Gates are **manual, operator-executed** steps run from the default profile BEFORE decomposition. They verify infrastructure health and plan readiness. They are NOT dispatched to workers.

### Gate 1 — Preflight (environment gating)

**Purpose:** Verify all infrastructure is healthy. Run from the **target repo root**.

```bash
bash "$HERMES_HOME/scripts/preflight.sh"
```

**Gate Verification:**
- Exit 0 → `status: pass` or `status: degraded` → proceed
- Exit 1 → `status: fail` → fix blocking failures, re-run

If degraded: review the JSON output for warnings. The smoke test can proceed with degraded status (e.g., API down when plan has no API dependency).

### Gate 2 — Pre-Dispatch Gate (plan + CLI + attestation)

**Purpose:** Verify the plan is on the working branch, coding agent is reachable, plan memory is seeded, and the kanban DB is healthy.

```bash
bash "$HERMES_HOME/scripts/pre_dispatch_gate.sh" kanban-standard-smoke-test
```

**Gate Verification:**
- Exit 0 → `[GATE] PASSED — proceed to decomposition` → proceed
- Exit 1 → `[GATE] BLOCKED — fix failures before dispatching` → fix and re-run

Common failure: `coding_agent_cli` — authenticate the coding CLI and re-run. If using `PREFLIGHT_SKIP_CODING_AGENT_CLI=1`, note that workers may fail on auth.

### Gate 3 — Handoff (create orchestrator handoff card)

**Purpose:** Create the handoff card that the orchestrator will decompose. Provisions wave crons (auto-unblock-1m, board-keeper-3m) before card creation.

```bash
python3 "$HERMES_HOME/scripts/kanban_handoff.py" \
  --plan .hermes/kanban/plans/kanban-standard-smoke-test.plan.md
```

If the plan is in a different location (e.g., `test-plan/`), pass the path relative to the target repo root:

```bash
python3 "$HERMES_HOME/scripts/kanban_handoff.py" \
  --plan test-plan/kanban-standard-smoke-test.plan.md
```

**Gate Verification:**
- Exit 0 → handoff card created with `Type: orchestrator-handoff`
- Exit 2 → orchestrator profile missing → create it: `hermes profile create orchestrator`
- Exit 3 → gateway not running → start gateway
- Exit 8 → cron provisioning failed → check `hermes` on PATH, gateway running

After handoff: the orchestrator receives the card, decomposes, and dispatches Cards 1–5. The operator monitors via `hermes kanban watch` or the board keeper cron.

<!-- /skip-validate -->

---

## Workstream 1 — Create Utility Module

**Priority:** 1 (no dependencies)

**File:** `test-plan/scripts/smoke_utils.py`
**Mode:** create-only

**Approach:** Create a Python utility module with three simple functions. Exercises basic agent code generation and the E001 (file compliance) gate.

### Card body

```agent
agent -p "Create test-plan/scripts/smoke_utils.py with three utility functions.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: create-only
Spec:
- def greet() -> str: returns 'hello from kanban'
- def add(a: int, b: int) -> int: returns a + b
- def format_name(first: str, last: str) -> str: returns '{last}, {first}' (Last, First format)
- Include a __main__ guard that runs all three and prints results
Call-sites: none (standalone utility module)
Forbidden: no external dependencies, no pip installs, no files outside Files: list
Acceptance:
- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files:
Tests: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('ALL TESTS PASSED')\"
Commit: feat: add smoke_utils module with greet, add, format_name
Diff cap: if >30 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 2 — Create Tests

**Priority:** 2 (depends on Card 1 — needs `test-plan/scripts/smoke_utils.py` to exist)

**File:** `test-plan/scripts/test_smoke_utils.py`
**Mode:** create-only

**Approach:** Create a proper pytest test file covering all three functions from Card 1. Tests edge cases: negative numbers for `add()`, single-name input for `format_name()`. Exercises E003 (test pass) and E021 (acceptance test coverage) gates.

### Card body

```agent
agent -p "Create test-plan/scripts/test_smoke_utils.py with pytest tests for smoke_utils.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/test_smoke_utils.py
Mode: create-only
Spec:
- test_greet_returns_string: calls greet(), asserts isinstance(result, str) and result != ''
- test_add_positive: add(2, 3) == 5
- test_add_negative: add(-1, -1) == -2
- test_add_zero: add(0, 5) == 5
- test_format_name_standard: format_name('Jane', 'Doe') == 'Doe, Jane'
- test_format_name_single: format_name('Madonna', '') == ', Madonna'
- Import smoke_utils from scripts.smoke_utils
Call-sites: none (test file, no production callers)
Forbidden: no new production files, no pip installs, no files outside Files: list
Acceptance:
- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files:
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: test: add pytest suite for smoke_utils
Diff cap: if >50 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 3 — Modify Utility Module (cross-file rebase)

**Priority:** 3 (depends on Cards 1 and 2 — modifies both files, needs Card 2's test file on its branch)

**Files:** `test-plan/scripts/smoke_utils.py` (modify-only), `test-plan/scripts/test_smoke_utils.py`
**Mode:** modify-only

**Approach:** Add a `multiply()` function to the existing module AND a corresponding test. Exercises E001 (modify-only file compliance), E003 (existing tests still pass), and same-file cross-card rebase (must merge Card 2's branch before modifying the test file).

### Card body

```agent
agent -p "Add a multiply() function to test-plan/scripts/smoke_utils.py and a test to test-plan/scripts/test_smoke_utils.py.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
Mode: modify-only
**Before modifying test-plan/scripts/test_smoke_utils.py, rebase on Card 2's work: git fetch origin {card2-branch} && git merge {card2-branch}.**
Spec:
- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
- Do NOT modify existing functions — only add the new one
- Do NOT create any new files
Call-sites: none (standalone utility function)
Forbidden: no new files, no pip installs, do not modify existing greet/add/format_name functions
Acceptance:
- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files; verify existing functions unchanged
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: feat: add multiply function to smoke_utils with tests
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 4 — Autonomous Recovery Test (Two-Layer)

**Priority:** 4 (depends on Card 3 completing first — needs the worktree to have current code)

**File:** `test-plan/scripts/smoke_utils.py`
**Mode:** modify-only

<!-- skip-validate V001 -- Workstream 4 approach: documentation references only, no work targets -->
**Approach:** This is the **autonomous error recovery demonstration card**. It exercises two recovery layers:

**Layer 1 — E002 Auto-Revert (worker-level, always tested):** The agent is instructed to do useful work (add a module docstring to `smoke_utils.py`, which IS on `Files:`) AND to intentionally create a scratchpad file (`_smoke_scratchpad.md`, which is NOT on `Files:`). The evaluation chain Step 2 (E002) detects the unlisted file and attempts to auto-revert it — without any human involvement. This proves the eval chain can autonomously recover from agent scope violations.

**Layer 2 — Final-Audit Remediation Loop (orchestrator-level, tested when violations exist):** If Cards 1–4 produce any latent issues that pass the eval chain but fail plan-level checks (e.g., a file the plan expected changes in but the agent didn't touch, or a cross-card regression from Card 3 → Card 4), the final audit (`final_audit_sanity.py --tier all`) detects them at Card 5 verification time and auto-spawns remediation cards. Workers pick up and fix those remediation cards autonomously. The smoke test PASSES whether the final audit exits 0 (clean) or exit 1 → remediation → exit 0 (self-healed).
<!-- /skip-validate -->

**What "remediation cards" means here:** In the kanban-advanced plugin, autonomous error recovery happens at two layers. The worker layer (E002 auto-revert) fixes scope violations inside the eval chain. The orchestrator layer (`final_audit_sanity.py --spawn-remediation`) creates actual `Type: remediation` kanban cards that workers claim and execute to fix post-merge issues. Card 4 triggers Layer 1. Card 5 exercises Layer 2.

### Card body

```agent
agent -p "Add a module-level docstring to scripts/smoke_utils.py AND create a scratchpad file.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: modify-only
Spec:
- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
- ALSO create test-plan/scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
Acceptance:
- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED autonomous recovery
Self-audit: before commit, confirm docstring added to smoke_utils.py only; do NOT commit the scratchpad file
Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
Commit: docs: add module docstring to smoke_utils
Diff cap: if >20 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

> **Operator note — what this card validates:**  
> - **Card completes →** E002 auto-revert succeeded. The eval chain detected the unlisted file and removed it. Check `scope_violations.jsonl` in the kanban logs for the recorded violation.  
> - **Card blocks →** E002 revert failed. The eval chain prevented unlisted changes from being committed. **Do NOT manually unblock this card.** Archiving it as blocked is a valid PASS — the governance gate is proven operational.  
> - **Either outcome = autonomous recovery demonstrated.** The system handled the error without a human touching `kanban unblock` or `kanban complete`.

---

## Workstream 5 — Verification and Remediation-Loop Exercise

**Priority:** 5 (depends on Cards 1–4 completing)

**Type:** verification-local

<!-- skip-validate V001 -- Workstream 5 approach: documentation references only, no work targets -->
**Approach:** Run the full test suite, then invoke the final audit pipeline. This card exercises the **orchestrator-level autonomous recovery mechanism** — the remediation-card loop.

**How the remediation loop works:**
1. `final_audit_sanity.py --tier all` checks the merged state of all completed cards against the plan
2. If violations detected → exit 1 → cards with `Type: remediation` are auto-created, assigned to workers
3. Workers autonomously pick up and fix remediation cards
4. Auto-unblock cron releases the audit card → re-runs `--tier all`
5. Loop repeats until exit 0 (clean) or max rounds exceeded

**In a clean run** (no latent issues from Cards 1–4), the audit exits 0 immediately — the remediation pipeline is structurally validated. **In a run with issues** (agent non-determinism), the remediation loop self-heals — proving autonomous recovery.
<!-- /skip-validate -->

### Card body

```
Type: verification-local
plan_id: kanban-standard-smoke-test
Acceptance:
- 1. Run test suite: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
- 2. Run final audit: python3 "$HERMES_HOME/scripts/final_audit_sanity.py" --plan-id kanban-standard-smoke-test --tier all
- 3. If audit exit 1: python3 "$HERMES_HOME/scripts/final_audit_sanity.py" --plan-id kanban-standard-smoke-test --spawn-remediation
     Wait for all remediation cards to reach done (hermes kanban list). Re-run step 2.
- 4. If audit exit 2: BLOCK — script error. Do NOT proceed. Investigate.
- 5. Generate token report: python3 "$HERMES_HOME/scripts/kanban_token_report.py" --plan kanban-standard-smoke-test
- 6. Generate postmortem: python3 "$HERMES_HOME/scripts/generate_postmortem.py" --plan-id kanban-standard-smoke-test
- 7. Verify artifacts: ls .hermes/kanban/reports/kanban-standard-smoke-test_*.md .hermes/kanban/reports/kanban-standard-smoke-test_kpi.json
- 8. Run reconciliation per kanban-advanced:kanban-reconciliation skill
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: N/A (verification only)
Mode: read-only
```

<!-- skip-validate V001 -- Operator note: documentation references only, no work targets -->
> **Operator note — how to FORCE-test the remediation loop:** If Cards 1–4 all complete perfectly and `final_audit_sanity.py --tier all` exits 0 (no violations), the remediation-card pipeline was NOT exercised. To explicitly validate it, after all cards complete but before running Card 5:  
> 1. Delete or rename one line from `test-plan/scripts/smoke_utils.py` (e.g., remove the `greet()` function)  
> 2. Commit the change on the working branch  
> 3. Run Card 5 normally  
> 4. `final_audit_sanity.py` will detect `plan_file_zero_diff` for `smoke_utils.py` against Card 1's baseline → exit 1 → spawn remediation cards → workers restore the function → re-audit exit 0.  
> 5. This proves the remediation-card autonomous recovery pipeline end-to-end.  
> 6. **After the test:** revert the manual change — the remediation worker already fixed it.
<!-- /skip-validate -->

---

## Kanban optimization

### Dependency graph

```
Card 1 (create test-plan/scripts/smoke_utils.py)
  └─→ Card 2 (create tests)
        └─→ Card 3 (modify smoke_utils + tests — cross-file rebase)
              └─→ Card 4 (autonomous recovery — E002 gate)
                    └─→ Card 5 (verification + final audit)
```

All cards are serial (wave_parent chain) because each depends on the prior card's output.

### Dispatch order

| Wave | Card | Title | Parallel? |
|------|------|-------|-----------|
| 1 | Card 1 | Create Utility Module | Solo |
| 2 | Card 2 | Create Tests | Solo (depends on Card 1) |
| 3 | Card 3 | Modify Utility Module | Solo (depends on Card 2) |
| 4 | Card 4 | Autonomous Recovery Test | Solo (depends on Card 3) |
| 5 | Card 5 | Verification + Final Audit | Solo (depends on Card 4) |

### Contracts

Contracts: none (all symbols are local to single cards — no shared functions, types, or constants span multiple card scopes)

---

#### Card 1 — Create Utility Module
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/smoke_utils.py
mode: create-only
wave: 1
assignee: kanban-advanced-worker
estimated_lines: 25

```agent
agent -p "Create scripts/smoke_utils.py with three utility functions.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: create-only
Spec:
- Create at test-plan/scripts/smoke_utils.py
- def greet() -> str: returns 'hello from kanban'
- def add(a: int, b: int) -> int: returns a + b
- def format_name(first: str, last: str) -> str: returns '{last}, {first}' (Last, First format)
- Include a __main__ guard that runs all three and prints results
Call-sites: none (standalone utility module)
Forbidden: no external dependencies, no pip installs, no files outside Files: list
Acceptance:
- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files:
Tests: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('ALL TESTS PASSED')\"
Commit: feat: add smoke_utils module with greet, add, format_name
Diff cap: if >30 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 2 — Create Tests
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/test_smoke_utils.py
mode: create-only
wave: 2
wave_parent: card1
assignee: kanban-advanced-worker
estimated_lines: 40

```agent
agent -p "Create test-plan/scripts/test_smoke_utils.py with pytest tests for smoke_utils.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/test_smoke_utils.py
Mode: create-only
Spec:
- test_greet_returns_string: calls greet(), asserts isinstance(result, str) and result != ''
- test_add_positive: add(2, 3) == 5
- test_add_negative: add(-1, -1) == -2
- test_add_zero: add(0, 5) == 5
- test_format_name_standard: format_name('Jane', 'Doe') == 'Doe, Jane'
- test_format_name_single: format_name('Madonna', '') == ', Madonna'
- Import smoke_utils from scripts.smoke_utils
Call-sites: none (test file, no production callers)
Forbidden: no new production files, no pip installs, no files outside Files: list
Acceptance:
- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files:
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: test: add pytest suite for smoke_utils
Diff cap: if >50 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 3 — Modify Utility Module
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/smoke_utils.py
  - test-plan/scripts/test_smoke_utils.py
mode: modify-only
wave: 3
wave_parent: card2
assignee: kanban-advanced-worker
estimated_lines: 35

```agent
agent -p "Add a multiply() function to scripts/smoke_utils.py and a test to scripts/test_smoke_utils.py.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
Mode: modify-only
**Before modifying test-plan/scripts/test_smoke_utils.py, rebase on Card 2's work: git fetch origin {card2-branch} && git merge {card2-branch}.**
Spec:
- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
- Do NOT modify existing functions — only add the new one
- Do NOT create any new files
Call-sites: none (standalone utility function)
Forbidden: no new files, no pip installs, do not modify existing greet/add/format_name functions
Acceptance:
- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert any file not in Files; verify existing functions unchanged
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: feat: add multiply function to smoke_utils with tests
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 4 — Autonomous Recovery Test (E002)
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/smoke_utils.py
mode: modify-only
wave: 4
wave_parent: card3
assignee: kanban-advanced-worker
estimated_lines: 10

```agent
agent -p "Add a module-level docstring to scripts/smoke_utils.py AND create a scratchpad file.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: modify-only
Spec:
- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
- ALSO create test-plan/scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
Acceptance:
- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED autonomous recovery
Self-audit: before commit, confirm docstring added to smoke_utils.py only; do NOT commit the scratchpad file
Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
Commit: docs: add module docstring to smoke_utils
Diff cap: if >20 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 5 — Verification and Remediation
plan_id: kanban-standard-smoke-test
type: verification-local
wave: 5
wave_parent: card4
assignee: kanban-advanced-orchestrator
estimated_lines: 0
Acceptance:
- 1. Run test suite: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
- 2. Run final audit: python3 scripts/final_audit_sanity.py --plan-id kanban-standard-smoke-test --tier all
- 3. If audit exit 1: python3 scripts/final_audit_sanity.py --plan-id kanban-standard-smoke-test --spawn-remediation
     Wait for all remediation cards to reach done (hermes kanban list). Re-run step 2.
- 4. If audit exit 2: BLOCK — script error. Do NOT proceed. Investigate.
- 5. Generate token report: python3 scripts/kanban_token_report.py --plan kanban-standard-smoke-test
- 6. Generate postmortem: python3 scripts/generate_postmortem.py --plan-id kanban-standard-smoke-test
- 7. Verify artifacts: ls .hermes/kanban/reports/kanban-standard-smoke-test_*.md .hermes/kanban/reports/kanban-standard-smoke-test_kpi.json
- 8. Run reconciliation per kanban-advanced:kanban-reconciliation skill
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: N/A (verification only)
Mode: read-only
```
