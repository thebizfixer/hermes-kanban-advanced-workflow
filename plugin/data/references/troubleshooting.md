# Troubleshooting — hermes-kanban-advanced-workflow

Common plugin/operator issues encountered during kanban runs and how to diagnose them.

## E001 false negative (Files: clobbered by worker_context)

**Symptom:** `step_1_file_compliance` passes despite `Files:` list being overwritten.

**Root cause:** `parse_card_body` in `card_body.py` handled YAML `files:` block but a trailing `Files: path (modify-only)` line from worker_context overwrote the list.

**Fix:** `parse_card_body` now guards with `and not files_line` when YAML `files:` already populated.

**Diagnose:** Inspect the card body with `hermes kanban show <task_id>` — if `Files:` shows a single file from worker_context but the plan lists multiple files, the guard worked but the evaluation chain may need re-run. Run `python3 scripts/kanban_evaluation_chain.py <task_id> <workspace>` to re-evaluate.

## Tests: line prose (Card 6 thrash)

**Symptom:** Card blocked >40 times with invalid Tests: line validation errors.

**Root cause:** Operator manual steps or matrix prose (e.g. "matrix v8 row 1 + row 2") placed in the `Tests:` field instead of `Acceptance:`.

**Fix:** `verify_optimization.sh` check 22 validates `Tests:` command syntax. `card_body_fidelity.py` flags prose signal words. `Type: verification-deploy` cards must use `Tests: N/A` with operator steps in `Acceptance:`.

**Prevent:** Use `N/A` for deploy/smoke cards; use `Tests: pytest tests/path.py -q` for code cards. Never write prose like "run r1 then r2" in Tests:.

## Lifecycle silent cron (blocked→running)

**Symptom:** Card transitions from blocked to running but no lifecycle notification fires.

**Root cause:** `kanban_lifecycle_notify.sh` only emitted on `ready→running` transitions. `blocked→running` (dispatch reclaim path) was silent.

**Fix:** Notification now fires on `blocked→running`, `ready→running`, and `None→running` transitions.

**Diagnose:** Check `.hermes/kanban/logs/lifecycle.jsonl` for missing transition entries. The transition event type should be "running" for all three paths.

## Docs staleness (Card 1 before Cards 2–5)

**Symptom:** Docs card archived as done but documentation describes pre-change state.

**Root cause:** Docs card dispatched in wave 1 while implementation cards followed in waves 2–5. The docs described stale thresholds, `[new]` tags, and `pending` references that became false after implementation merged.

**Fix:** Apply docs-last decomposition rule. See `kanban-planning` § Decomposition rules.

**Detection:** `verify_optimization.sh` check 24 (inverted-graph WARN) flags docs cards before their referenced implementation cards. `kanban_evaluation_chain.py` step E022 (docs HEAD verify) runs Verify: rg commands against HEAD and flags stale markers.

## Reconciliation vs postmortem

**Boundary:** The postmortem (`{plan_id}_postmortem_{date}.md`) covers **project outcomes** — what shipped, what didn't, acceptance gaps. The reconciliation sidecar (`{plan_id}_reconciliation_{date}.md`) covers **machinery health** — evaluation chain performance, parser misses, thrash patterns, scope violations. Use the reconciliation to tune the kanban-advanced workflow; use the postmortem to report to stakeholders.
