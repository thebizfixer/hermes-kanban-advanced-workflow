# test-plan — Kanban Advanced Example Test Plan & Artifacts

This folder contains a complete example plan and its supporting artifacts for the `kanban-advanced` Hermes Agent plugin. Use it to calibrate your plugin installation and verify that the governance pipeline (preflight → attest → decompose → evaluation chain → audit → reconcile → postmortem) works end-to-end before you run your own production plans.

## Contents

| File | Purpose |
|------|---------|
| `kanban-standard-smoke-test.plan.md` | A standardized smoke test plan (5 cards: create utilities, test them, modify, negative governance test, verification) that exercises every phase of the kanban-advanced SOP. |
| `kanban-advanced-governance-hardening.plan.md` | Plan for hardening the plugin itself (AGT/AEP governance fidelity, verification exemptions, token metering, escalation, hard-stop enforcement). Reference example of a self-improvement plan. |
| `scripts/smoke_utils.py` | The utility module created and modified by the smoke test (greet, add, format_name, multiply). |
| `scripts/test_smoke_utils.py` | Pytest suite for the utility module (8 tests across 4 classes). |
| `artifacts/` | Post-run artifacts (postmortem, KPI JSON, reconciliation reports) — populated after each clean run. |

## How to Use

1. **Install the plugin** if you haven't already:
   ```bash
   hermes plugins install thebizfixer/hermes-kanban-advanced-workflow
   ```

2. **Initialize** your project (replace `<your-project>` and `<branch>`):
   ```bash
   cd <your-project>
   hermes kanban-advanced init --project-root . --working-branch <branch>
   ```

3. **Copy the test plan** into your project's kanban plans directory:
   ```bash
   cp test-plan/kanban-standard-smoke-test.plan.md .hermes/kanban/plans/
   cp test-plan/scripts/* scripts/
   ```

4. **Run the full SOP** — from planning through postmortem (see [README.md](../README.md) for the flowchart):
   - "Optimize for Kanban"
   - Confirm preflight + attest + decompose
   - "Execute the plan"
   - Monitor, reconcile, cleanup, postmortem

5. **Verify your results** match the expected output:
   - 8/8 tests pass (greet, add, format_name, multiply)
   - Evaluation chain gates exercised (E002 governance, E018 token exactness)
   - Escalation ladder demonstrated (board-keeper → tracker → orchestrator)
   - Postmortem generated with token economics + KPI JSON

## What Good Output Looks Like

After a clean run, you should see:
- **Board**: 5 work cards + gate + decompose + audit, all completed
- **Tests**: `python -m pytest scripts/test_smoke_utils.py -v` → 8 passed
- **Postmortem**: `<plan_id>_postmortem_<date>.md` with execution summary, token economics, agent performance, pitfalls
- **KPI JSON**: `<plan_id>_kpi.json` with success rate, intervention rate, thrash outliers, blocker chains
- **Reconciliation**: `<plan_id>_reconciliation_<date>.md` with thrash analysis, parser health, audit health

## Plugin Origin

This test plan targets the plugin installation at `hermes-kanban-advanced-workflow/`. When you copy it to your project, update any absolute paths to match your local plugin location. The plan uses `coding_agent_binary: hermes` (Hermes Agent itself as the coding agent) and `policy_profile: balanced` by default — adjust to your preferred agent and strictness level.

## Status

- [ ] Clean run pending
- [ ] Artifacts to be pushed after successful execution
- [ ] Postmortem and KPI to be added to `artifacts/`

---

**Primary docs:** [../README.md](../README.md) | [wiki/governance.md](../wiki/governance.md) | [docs/tutorial/kanban-advanced-tutorial.md](../docs/tutorial/kanban-advanced-tutorial.md)
