---
name: Smoke Test Bug Fixes and Hardening
plan_id: smoke-test-fixes
line_budget: 300
overview: >
  Fix 11 bugs discovered during kanban-standard-smoke-test execution,
  harden cron launchers against Windows path mangling, and document
  three known Hermes core limitations. This plan is the reconciliation
  output from the smoke test run on 2026-06-23.
isProject: false
optimization_checklist:
  plan_committed: pass
contingencies:
  - risk: "Git Bash not at expected path (C:/Program Files/Git/usr/bin/bash.exe)"
    probability: Low
    impact: BLOCKING
    mitigation: "Detect Git Bash path dynamically in launcher scripts"
    auto_retry: false
  - risk: "delegate_task subagents remain unreliable on Windows"
    probability: High
    impact: DEGRADED
    mitigation: "Disable parallel subagent gate on Windows; document as known limitation"
    auto_retry: true
todos:
  - id: fix-cron-launchers
    content: "Harden cron .py launchers: use full Git Bash path, subprocess.run instead of execvp, locate repo root for lifecycle script"
    status: pending
  - id: fix-handoff-force
    content: "Fix kanban_handoff.py --force to archive non-running cards even when running cards exist for the same plan_id"
    status: pending
  - id: fix-decompose-worktree
    content: "Fix kanban_decompose.py to auto-generate platform-appropriate worktree paths (platform temp dir, not /tmp)"
    status: pending
  - id: fix-gate-windows-paths
    content: "Fix pre_dispatch_gate.sh Windows path issues: kanban_db unicode escape, cron_scripts test -x, source errors"
    status: pending
  - id: fix-import-paths
    content: "Fix from card_body import -> from lib.card_body in 7 Python scripts"
    status: pending
  - id: doc-delegate-task-windows
    content: "Document delegate_task subagent unreliability on Windows as known limitation"
    status: pending
  - id: doc-todo-trap
    content: "Document cards unblocking to todo instead of ready on Windows"
    status: pending
  - id: doc-cron-path-bug
    content: "Reference Hermes core issue #23404 for cron bash path mangling on Windows"
    status: pending
---

# Smoke Test Bug Fixes and Hardening

> **Source:** Reconciliation from kanban-standard-smoke-test execution on 2026-06-23.
> **Test results:** 3/5 cards completed by workers, Card 4 blocked by E001 (subagent zero-output), Card 5 manually completed. 8/8 tests passing.

## Executive Summary

The smoke test exposed 11 plugin bugs (all fixed and pushed in 11 commits) and 3 Hermes core limitations on Windows. The fixes span import resolution, Windows path handling, cron script execution, decomposer workspace generation, and handoff idempotency. The remaining issues are upstream Hermes bugs requiring core fixes.

## Root Causes

| Bug | Root Cause | Fix Complexity |
|-----|-----------|----------------|
| `ModuleNotFoundError: card_body` | Absolute import `from card_body` when `scripts/lib/` not on `sys.path` | Trivial (1 line × 7 files) |
| Gate `kanban_db` FAIL | Python `\U` unicode escape in Windows path string | Trivial (use `os.path.join`) |
| Gate exit 1 after PASS | `source coding_agent_env.sh` failed + `set -e` | Trivial (`|| true`) |
| Decomposer `AttributeError: gate_id` | `--gate-id` arg used but never added to argparse | Trivial (1 line) |
| All gate checks FAIL via eval | Backslashes in `bundle_path` mangled by bash eval | Trivial (forward slashes in config) |
| `--force` refused with running card | Running check before archive pass | Simple (reorder logic) |
| Cron provision exit 127 | `subprocess.run` list args → no MSYS path translation | Simple (`shell=True`) |
| Cron scripts exit 127 (YAML) | `workdir` backslashes mangled by YAML parser | Simple (remove workdir) |
| Worker spawn failed: non-absolute worktree | Bare `worktree` or Unix `/tmp/` on Windows | Simple (platform temp dir) |
| Cron scripts exit 127 (bash) | Hermes core #23404: `str(path)` produces backslashes | Moderate (.py launchers) |
| Launcher stdout swallowed | `os.execvp` kills Python → cron pipe breaks; MSYS paths fail outside git-bash | Moderate (subprocess.run + Git Bash full path) |

## Already Shipped (11 commits on main)

All fixes pushed to `thebizfixer/hermes-kanban-advanced-workflow`:
1. `68bc14f` — Import paths (`from card_body` → `from lib.card_body`)
2. `af3dd7a` — Missing `--gate-id` arg + guarded source errors
3. `49f4aac` — `--force` archives non-running cards + removed `--workdir` from crons
4. `6bc060f` — `shell=True` for cron provision subprocess
5. `af8db06` — Auto-generated worktree paths use platform temp dir
6. `d0936c6` — Platform temp dir (was `/tmp`, invalid on Windows)
7. `a48c5c0` — `.py` launchers for cron bash scripts
8. `68d45ea` — `subprocess.run` with `shell=True` + MSYS paths for cron launchers
9. Plus overlay config changes (forward-slash `bundle_path`, `plan_search_dirs` with `test-plan`)

## Known Remaining Issues (Hermes Core)

| Issue | Impact | Reference |
|-------|--------|-----------|
| `delegate_task` subagents unreliable on Windows | Parallel gate crashes; Card 4 zero-output | Same root as orchestrator crashes |
| Cards unblock to `todo` instead of `ready` | Cards get stuck indefinitely with `auto_decompose: false` | Hit Card 2, Card 5 |
| Cron bash path mangling | Exit 127 on all `.sh` script crons | [Hermes #23404](https://github.com/NousResearch/hermes-agent/issues/23404) |

## Key Performance Targets

| Metric | Before | After |
|--------|--------|-------|
| Gate pass rate | 0% (8 failures) | 100% (0 failures, 2 warnings) |
| Cron success rate | 0% (exit 127) | 100% (all `last_status: ok`) |
| Worker spawn rate | 0% (non-absolute worktree) | 100% (platform temp dir) |
| Handoff duplicate rate | 100% (every run duped) | 0% (single decompose per run) |
| Card completion rate | 0% | 60% (3/5 auto; Card 4 manual, Card 5 stuck) |

---

## Workstream 1 — Harden Cron Launchers

**Priority:** 1 (no dependencies)

**Files:** `scripts/auto_unblock.py`, `scripts/board_keeper.py`, `scripts/kanban_lifecycle_notify.py`

**Approach:** The current `.py` launchers use `subprocess.run` with `shell=True` and the full Git Bash path. Verify they work from the cron runner's Windows process (not just git-bash terminal). Add fallback Git Bash path detection.

**Tests:** `python3 scripts/auto_unblock.py --dry-run` produces output; cron `last_status: ok`

```agent
agent -p "Harden cron .py launchers for Windows reliability.
plan_id: smoke-test-fixes
Files: scripts/auto_unblock.py, scripts/board_keeper.py, scripts/kanban_lifecycle_notify.py
Mode: modify-only
Spec:
- Detect Git Bash path dynamically: try common locations (C:/Program Files/Git/usr/bin/bash.exe, C:/Git/usr/bin/bash.exe), fall back to 'bash' on PATH
- Add timeout handling for subprocess.run
- Add error logging to stderr when bash exits non-zero
- Lifecycle launcher: improve repo root detection — check HERMES_KANBAN_REPO_ROOT env var, search from common project roots
Acceptance:
- Done when: all three launchers produce correct output when invoked from non-git-bash Python process
- Verify: python3 -c "import subprocess; subprocess.run(['python3', 'scripts/auto_unblock.py', '--dry-run'], capture_output=True)" shows exit 0 with output
Tests: python3 scripts/auto_unblock.py --dry-run && python3 scripts/kanban_lifecycle_notify.py
Commit: fix: harden cron launchers with dynamic Git Bash detection and timeout handling
Do NOT push to main — commit to worktree branch only."
```

---

## Workstream 2 — Document Known Windows Limitations

**Priority:** 2 (depends on nothing — docs only)

**Files:** `PLATFORM_NOTES.md`, `wiki/troubleshooting.md`

**Approach:** Document three known Hermes core issues discovered during smoke test: delegate_task subagent unreliability, todo status trap, and cron bash path mangling (#23404). Add workarounds where available.

```agent
agent -p "Document Windows-specific known limitations discovered during smoke test.
plan_id: smoke-test-fixes
Files: PLATFORM_NOTES.md, wiki/troubleshooting.md
Mode: modify-only
Spec:
- Add section to PLATFORM_NOTES.md: 'Known Hermes Core Limitations on Windows' with three subsections:
  1. delegate_task subagents: describe symptom (subagents never complete in kanban worker sessions), workaround (disable parallel subagent gate via overlay config)
  2. todo status trap: describe symptom (unblocked cards land in todo instead of ready), workaround (manually complete stuck cards; board-keeper rule pending)
  3. Cron bash path mangling: reference Hermes #23404, describe workaround (.py launchers with full Git Bash path)
- Add cross-reference in wiki/troubleshooting.md under Windows section
Acceptance:
- Done when: PLATFORM_NOTES.md has all three subsections, wiki cross-references exist
- Verify: grep -c 'delegate_task' PLATFORM_NOTES.md && grep -c 'todo.*trap' PLATFORM_NOTES.md
Tests: grep -c 'delegate_task.*Windows' PLATFORM_NOTES.md
Commit: docs: document Windows-specific known limitations from smoke test
Do NOT push to main — commit to worktree branch only."
```

## Kanban optimization

### Dependency graph

```
Card 1 (launchers) ──┐
                      ├── Card 3 (verify + reconcile)
Card 2 (docs) ───────┘
```

Wave 1: Cards 1 and 2 in parallel (no dependencies between them)
Wave 2: Card 3 gates on both (verification + reconciliation closeout)

| Parent | Child | Reason |
|--------|-------|--------|
| card1 | card3 | Launcher fixes must be verified |
| card2 | card3 | Docs must be complete before closeout |

#### Card 1 — Harden Cron Launchers
plan_id: smoke-test-fixes
files:
  - scripts/auto_unblock.py
  - scripts/board_keeper.py
  - scripts/kanban_lifecycle_notify.py
mode: modify-only
wave: 1
estimated_lines: 40
assignee: kanban-advanced-worker

```agent
agent -p "Harden cron .py launchers for Windows reliability.
plan_id: smoke-test-fixes
Files: scripts/auto_unblock.py, scripts/board_keeper.py, scripts/kanban_lifecycle_notify.py
Mode: modify-only
Spec:
- Detect Git Bash path dynamically: try common locations, fall back to 'bash' on PATH
- Add subprocess timeout handling with meaningful error messages
- Lifecycle launcher: check HERMES_KANBAN_REPO_ROOT env var first, then search from common roots
Acceptance:
- Done when: all three launchers work from non-git-bash Python process
- Verify: python3 scripts/auto_unblock.py --dry-run produces output
Tests: for f in auto_unblock.py board_keeper.py kanban_lifecycle_notify.py; do python3 scripts/$f --dry-run 2>&1 | head -1; done
Commit: fix: harden cron launchers with dynamic Git Bash detection
Do NOT push to main — commit to worktree branch only."
```

#### Card 2 — Document Windows Limitations
plan_id: smoke-test-fixes
files:
  - PLATFORM_NOTES.md
  - wiki/troubleshooting.md
mode: modify-only
wave: 1
estimated_lines: 50
assignee: kanban-advanced-worker

```agent
agent -p "Document Windows-specific known limitations from smoke test.
plan_id: smoke-test-fixes
Files: PLATFORM_NOTES.md, wiki/troubleshooting.md
Mode: modify-only
Spec:
- Add 'Known Hermes Core Limitations on Windows' section to PLATFORM_NOTES.md:
  1. delegate_task subagents (symptom + workaround: disable parallel gate)
  2. todo status trap (symptom + workaround: manual complete + board-keeper rule pending)
  3. Cron bash path mangling (link to #23404 + workaround: .py launchers)
- Add cross-reference row in wiki/troubleshooting.md Windows section
Acceptance:
- Done when: all three subsections in PLATFORM_NOTES.md, wiki cross-reference exists
- Verify: grep -c 'delegate_task.*Windows' PLATFORM_NOTES.md
Tests: grep -c '### Known Hermes Core Limitations' PLATFORM_NOTES.md
Commit: docs: document Windows-specific limitations from smoke test
Do NOT push to main — commit to worktree branch only."
```

#### Card 3 — Verification and Reconciliation Closeout
plan_id: smoke-test-fixes
Type: verification
wave: 2
wave_parent: card1
ordinal_parent: card2
assignee: kanban-advanced-orchestrator
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts

```agent
agent -p "Verify smoke test fixes and run reconciliation.
plan_id: smoke-test-fixes
Acceptance:
- Done when: all 8 smoke tests pass, launchers verified, docs complete, reconciliation report written
- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v --rootdir=test-plan/scripts
Commit: chore: reconciliation closeout for smoke-test-fixes
Do NOT push to main — commit to worktree branch only."
```
