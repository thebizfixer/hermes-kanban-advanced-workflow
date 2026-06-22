---
name: Kanban Standard Smoke Test
plan_id: kanban-standard-smoke-test
line_budget: 200
overview: >
  Standardized end-to-end validation test for the kanban-advanced plugin.
  Verifies card body parsing, coding-agent dispatch, eval chain governance
  (E001–E023), token logging (E018/E020), postmortem generation, and
  reconciliation. Ships with the plugin as a self-diagnostic for new
  installations. Produces example postmortem/KPI artifacts demonstrating
  post-execution success.
isProject: false
optimization_checklist:
  plan_committed: pass
contingencies:
  - risk: "Coding agent not configured (KANBAN_CODING_AGENT unset or binary missing)"
    probability: High
    impact: BLOCKING
    mitigation: "Run `hermes kanban-advanced init` and set `coding_agent_binary` in kanban-config.yaml. See `plugin/data/references/coding-agent-auth.md`."
    auto_retry: false
  - risk: "Coding agent auth failure (OAuth expired / API key missing)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Authenticate coding CLI per `plugin/data/references/coding-agent-auth.md`. Re-run preflight after auth fix."
    auto_retry: false
  - risk: "Token tracker unavailable (scripts/token_tracker.py not provisioned)"
    probability: Low
    impact: BLOCKING
    mitigation: "Re-run `hermes kanban-advanced init` or `Update Plugin` to provision token_tracker.py."
    auto_retry: false
  - risk: "Eval chain script missing (scripts/kanban_evaluation_chain.py not found)"
    probability: Low
    impact: BLOCKING
    mitigation: "Run `Update Plugin` to restore scripts. Verify with: ls scripts/kanban_evaluation_chain.py"
    auto_retry: false
  - risk: "E002 unlisted changes blocks Card 4 (negative test — expected behavior)"
    probability: Expected
    impact: DEGRADED
    mitigation: "Card 4 intentionally creates a file outside Files: scope. Verify the block message contains E002_UNLISTED_FILE_CHANGE. Archive the blocked card — this confirms the governance gate works."
    auto_retry: false
  - risk: "E020/E018 token logging blocked — coding agent produces no JSON usage block (aider only; hermes now uses authoritative insights metering via hermes_token_meter.py + E018 accepts hermes_insights source)"
    probability: Medium
    impact: BLOCKING
    mitigation: "For hermes: hermes_token_meter.py snapshots insights before dispatch and computes deltas after — no JSON output needed. For aider: character-count estimation via Tier 3. For JSON-output agents (Cursor, Claude Code, Codex): capture agent stdout to /tmp/agent_output_<task_id>.json with usage block. See § Token Logging below for tier details."
    auto_retry: false
  - risk: "Gateway not running (dispatcher won't pick up cards)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Start gateway: `hermes gateway run` (or Windows scheduled task). Verify: `hermes kanban list` shows cards."
    auto_retry: false
  - risk: "Subagent gate interrupted (parallel subagents crash mid-exec)"
    probability: Medium
    impact: BLOCKING
    mitigation: "Known infrastructure issue — delegation subagents may be interrupted. Fall back to serial gate: set `subagent_gate: false` in kanban-config.yaml, then run pre_dispatch_gate.sh directly."
    auto_retry: false
  - risk: "Missing or incomplete hermes_insights deltas at orchestrator checkpoints"
    probability: Medium
    impact: BLOCKING
    mitigation: "Orchestrator must emit planning-complete, decompose-complete, audit-start, and cleanup-complete checkpoints using hermes_token_meter + insights. Verify deltas appear in tokens.jsonl and postmortem."
    auto_retry: false
  - risk: "Insufficient negative/governance test coverage"
    probability: Medium
    impact: DEGRADED
    mitigation: "Add deliberate malformed-block, budget-violation, and circular-dep negative tests. Archive blocked cards only after confirming exact E00x messages."
    auto_retry: false
  - risk: "No formal preflight/attestation step before decompose"
    probability: Low
    impact: BLOCKING
    mitigation: "Run explicit preflight checklist (env, profiles, scripts, gateway, token tracker, kanban-config, DB integrity) and attest before creating root/gate cards."
    auto_retry: false
todos:
  - id: card-preflight
    content: "Preflight & Attestation: verify env, profiles, scripts, gateway, token tracker, kanban-config, DB integrity before any decomposition"
    status: pending
  - id: card-1-utils
    content: "Create test-plan/scripts/smoke_utils.py with utility functions (greet, add, format_name)"
    status: pending
  - id: card-2-tests
    content: "Create test-plan/scripts/test_smoke_utils.py with pytest tests for all three functions"
    status: pending
  - id: card-3-modify
    content: "Modify test-plan/scripts/smoke_utils.py to add a multiply() function (modify-only mode)"
    status: pending
  - id: card-4-e002-test
    content: "Negative governance test: agent attempts to create a file NOT on Files: (should trigger E002 block)"
    status: pending
  - id: card-5-verify
    content: "Verification card: run test suite, check token log exists, confirm all artifacts"
    status: pending
---

# Kanban Standard Smoke Test

> **Purpose:** Validate a kanban-advanced installation end-to-end. Run after `hermes kanban-advanced init` to confirm the plugin is correctly provisioned, the coding agent dispatches and produces verifiable output, all evaluation chain gates function, and postmortem artifacts are generated correctly.

> **Prerequisites:**
> - Hermes Agent ≥ 0.16.0
> - `hermes kanban-advanced init` completed successfully
> - Coding agent binary configured in `.hermes/kanban-overrides/kanban-config.yaml` (`coding_agent_binary`)
> - Coding agent authenticated (see `plugin/data/references/coding-agent-auth.md`)
> - Gateway running (`hermes gateway run` or scheduled task)
> - Working directory: host project repo root

> **Expected duration:** 15–30 minutes (depends on coding agent speed)
> **Expected outcome:** 4 code-gen cards dispatched, 3 completed (Cards 1–3), 1 blocked (Card 4 — E002 expected), 1 verification card passed (Card 5). Postmortem generated at `.hermes/kanban/reports/kanban-standard-smoke-test_postmortem_*.md`. Token log populated at `~/.hermes/kanban/tokens.jsonl` with entries for all completed cards.

> **Success criteria:**
> - [ ] Preflight & attestation checklist passed before any decomposition
> - [ ] Card 1 completed: `test-plan/scripts/smoke_utils.py` exists with `greet()`, `add()`, `format_name()`
> - [ ] Card 2 completed: `test-plan/scripts/test_smoke_utils.py` exists, tests pass
> - [ ] Card 3 completed: `multiply()` added to `test-plan/scripts/smoke_utils.py`, tests updated and pass
> - [ ] Card 4 blocked: E002_UNLISTED_FILE_CHANGE detected, unlisted file auto-reverted
> - [ ] Card 5 completed: test suite passes, token log has entries, artifacts exist
> - [ ] hermes_insights deltas present at all four orchestrator checkpoints (planning/decompose/audit/cleanup)
> - [ ] Token log shows separate input/output/cache where available; Effective Tokens (or equivalent) calculated in postmortem
> - [ ] ≥2 negative/governance tests executed (E002 + at least one malformed-block or budget test)
> - [ ] Reconciliation covers: file compliance, token burn accuracy, governance taxonomy, state, and delta vs prior run
> - [ ] Postmortem generated with KPI JSON, reconciliation sidecar, and concrete action items (owner + deadline)
> - [ ] Postmortem is blameless and includes decision-path / tool-usage traces for main cards
> - [ ] Token log (`tokens.jsonl`) has entries for completed cards + orchestrator checkpoints
> - [ ] Reconciliation report confirms ≥80% success rate and 0 un-reconciled governance violations

---

## Architecture Notes

### Token Logging

The kanban-advanced plugin supports three tiers of token metering, selected automatically based on the configured coding agent binary:

| Tier | Source | Agents | Mechanism |
|------|--------|--------|-----------|
| 1 | `agent` | Cursor, Claude Code, Codex, Gemini, Grok | Exact from agent JSON `usage` block |
| 2 | `hermes_insights` | hermes | Authoritative — Hermes insights delta (provider response headers, not self-reported) |
| 3 | `estimated` | aider, unknown binaries | Character-count estimation from agent output |

**The `hermes` coding agent** uses Tier 2: hermes_token_meter.py snapshots Hermes token state before dispatch, computes the delta after dispatch, and logs authoritative counts to `tokens.jsonl`. This is NOT self-reported — it comes from Hermes' own provider accounting.

**Orchestrator checkpoints (mandatory for walk-away mode):**
- planning-complete
- decompose-complete
- audit-start
- cleanup-complete

All four must log via hermes_insights delta. Deltas must appear in the project `.hermes/kanban/tokens.jsonl`.

**Observability requirements (drawn from industry best practices for AI agent workflows):**
- Track across the full decision chain (not just final output).
- Log input / output / cache tokens separately.
- Compute weighted "Effective Tokens" style metric in postmortem (model cost multiplier × (I + 0.1×C + 4×O)).
- Enforce workflow-level budget thresholds for the smoke test run.
- Capture decision paths, tool calls, and per-step spend for traceability and audit.

**The `aider` coding agent** uses Tier 3 estimation. aider produces text-only output with no JSON usage block and no integration with Hermes insights. Consider configuring a JSON-output coding agent for exact token tracking.

**How to check your coding agent:**
```bash
grep 'coding_agent_binary' .hermes/kanban-overrides/kanban-config.yaml
# Expected values with full token support: agent, cursor-agent, claude, codex, gemini, grok, hermes
# Estimated-only: aider
```

---


**Escalation demo (for next run):** Card 4 (E002 negative test) is expected to block at least twice.
Board-keeper detects the second block (re-block count >=2), forces `[escalation:worker:attempt:2]`,
calls tracker, and escalates to orchestrator (unblocks with tag + comment). Orchestrator resolves
before a third block. Additionally, if any card accumulates 5 identical error blocks, the board-keeper's
conversation cap forces immediate escalation to orchestrator (E023 error attractors in the eval chain
provide a first line of defense — short-circuiting repeated identical failures before they reach 5 loops). Use local override `escalation_max_attempts.worker: 2` (orchestrator: 1-2)
for the smoke test to make thresholds hit cleanly at 2.

## Workstream 1 — Create Utility Module

**Priority:** 1 (no dependencies)

**File:** `test-plan/scripts/smoke_utils.py`
**Mode:** create-only

**Approach:** Create a Python utility module with three simple functions that cover different code patterns (string return, arithmetic, string formatting). This exercises basic agent code generation and the E001 (file compliance) gate.

**Tests:** Included inline — the agent creates both the module and an inline assertion.

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
Acceptance:
- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
Tests: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('ALL TESTS PASSED')\"
Commit: feat: add smoke_utils module with greet, add, format_name
Diff cap: if >30 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 2 — Create Tests

**Priority:** 2 (depends on Card 1 — needs test-plan/scripts/smoke_utils.py to exist)

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
Acceptance:
- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: test: add pytest suite for smoke_utils
Diff cap: if >50 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 3 — Modify Utility Module

**Priority:** 3 (depends on Cards 1 and 2 — modifies test-plan/scripts/smoke_utils.py, needs tests to exist for verification)

**File:** `test-plan/scripts/smoke_utils.py`
**Mode:** modify-only

**Approach:** Add a `multiply()` function to the existing module AND add a corresponding test to the test file. This exercises E001 (modify-only file compliance), E003 (existing tests still pass), and E017 (excessive churn — should be well under budget).

### Card body

```agent
agent -p "Add a multiply() function to test-plan/scripts/smoke_utils.py and a test to test-plan/scripts/test_smoke_utils.py.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
Mode: modify-only
Spec:
- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
- Do NOT modify existing functions — only add the new one
- Do NOT create any new files
Acceptance:
- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: feat: add multiply function to smoke_utils with tests
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 4 — Negative Governance Test (E002 Gate)

**Priority:** 4 (depends on Card 3 completing first — needs the worktree to have current code)

**File:** `test-plan/scripts/smoke_utils.py`
**Mode:** modify-only

**Approach:** This card **intentionally** instructs the agent to create a file NOT listed in `Files:`. The agent is told to add a docstring to `test-plan/scripts/smoke_utils.py` (which is on `Files:`) BUT ALSO to create a `scripts/_smoke_scratchpad.md` file (which is NOT on `Files:`). The evaluation chain Step 2 (E002) should detect the unlisted file and auto-revert it. If the revert succeeds, the card completes. If unlisted changes remain after revert, the card blocks.

**Expected behavior:** E002_UNLISTED_FILE_CHANGE triggers. The unlisted file is either auto-reverted (card completes with warning) or blocks if revert fails. Either outcome is valid — the test verifies that the E002 gate is operational.

### Card body

```agent
agent -p "Add a module-level docstring to test-plan/scripts/smoke_utils.py AND create a scratchpad file.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: modify-only
Spec:
- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
- ALSO create scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
Acceptance:
- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED
Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
Commit: docs: add module docstring to smoke_utils
Diff cap: if >20 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

> **Operator note:** If this card completes (E002 auto-revert succeeded), the governance gate worked silently — the unlisted file was created then removed. Check `scope_violations.jsonl` in the kanban logs for the recorded violation. If this card blocks (E002 revert failed), the gate prevented unlisted changes from being committed — archive the blocked card. Either result validates the E002 gate.

---

## Workstream 5 — Verification and Artifact Check

**Priority:** 5 (depends on Cards 1–4 completing)

**Type:** verification-local

**Approach:** Run the full test suite and verify that all expected artifacts exist. This card does NOT invoke a coding agent — it's a supervisor-worker card that validates the entire test run's outputs.

### Card body

```
Type: verification-local
plan_id: kanban-standard-smoke-test
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: N/A (verification only)
Mode: read-only
```

**Additional verification checks (run manually after card completion):**

```bash
# 1. Token log populated
python3 scripts/kanban_token_report.py --plan kanban-standard-smoke-test

# 2. Postmortem generated (run after all cards complete)
python3 scripts/generate_postmortem.py --plan-id kanban-standard-smoke-test

# 3. Verify postmortem artifacts exist
ls -la .hermes/kanban/reports/kanban-standard-smoke-test_*.md
ls -la .hermes/kanban/reports/kanban-standard-smoke-test_kpi.json

# 4. Run reconciliation
# Follow kanban-advanced:kanban-reconciliation skill
```

---

## Kanban optimization

### Dependency graph

```
Card 1 (create test-plan/scripts/smoke_utils.py)
  └─→ Card 2 (create tests)
        └─→ Card 3 (modify smoke_utils + tests)
              └─→ Card 4 (negative E002 test)
                    └─→ Card 5 (verification + artifact check)
```

| Parent | Child | Relationship |
|--------|-------|-------------|
| — | Card 1 | Root — no dependencies |
| Card 1 | Card 2 | Card 2 needs test-plan/scripts/smoke_utils.py to exist |
| Card 2 | Card 3 | Card 3 modifies files Card 2 tests; needs tests as safety net |
| Card 3 | Card 4 | Card 4 runs after module is stable to test E002 gate cleanly |
| Card 4 | Card 5 | Card 5 verifies everything after all cards complete |

All cards are serial (wave_parent chain) because each depends on the prior card's output file.

### Dispatch order

| Wave | Cards | Parallel? |
|------|-------|-----------|
| 1 | Card 1 — Create Utility Module | Solo |
| 2 | Card 2 — Create Tests | Solo (depends on Card 1) |
| 3 | Card 3 — Modify Utility Module | Solo (depends on Card 2) |
| 4 | Card 4 — Negative E002 Test | Solo (depends on Card 3) |
| 5 | Card 5 — Verification | Solo (depends on Card 4) |

---

#### Card 1 — Create Utility Module
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/smoke_utils.py
mode: create-only
wave: 1
estimated_lines: 25

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
Acceptance:
- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
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
Acceptance:
- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
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
estimated_lines: 35

```agent
agent -p "Add a multiply() function to test-plan/scripts/smoke_utils.py and a test to test-plan/scripts/test_smoke_utils.py.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
Mode: modify-only
Spec:
- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
- Do NOT modify existing functions — only add the new one
- Do NOT create any new files
Acceptance:
- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: feat: add multiply function to smoke_utils with tests
Diff cap: if >40 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 4 — Negative Governance Test (E002)
plan_id: kanban-standard-smoke-test
files:
  - test-plan/scripts/smoke_utils.py
mode: modify-only
wave: 4
wave_parent: card3
estimated_lines: 10

```agent
agent -p "Add a module-level docstring to test-plan/scripts/smoke_utils.py AND create a scratchpad file.
plan_id: kanban-standard-smoke-test
Files: test-plan/scripts/smoke_utils.py
Mode: modify-only
Spec:
- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
- ALSO create scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
Acceptance:
- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED
Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
Commit: docs: add module docstring to smoke_utils
Diff cap: if >20 net lines, STOP and report.
Do NOT push to main — commit to worktree branch only."
```

#### Card 5 — Verification and Artifact Check
plan_id: kanban-standard-smoke-test
type: verification-local
wave: 5
wave_parent: card4
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: N/A (verification only)
Mode: read-only
