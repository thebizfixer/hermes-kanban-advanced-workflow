---
name: kanban-reconciliation
description: Post-execution reconciliation checklist — file compliance, token burn, skill updates, and board cleanup. Maps to Six Sigma DMAIC (Define → Measure → Analyze → Improve → Control).
version: 1.1.0
metadata:
  hermes:
    tags: [kanban, reconciliation, audit, six-sigma]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-postmortem]
---

# Kanban Reconciliation

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Run after every plan execution. Systematic checklist to close the loop and prevent drift. The reconciliation report serves as the change log for the entire plan — be specific about files, commits, and decisions. If something went wrong during execution, take a step back and think through what happened before writing the reconciliation.

## KPI targets

Every reconciliation report must surface these metrics against their targets:

| KPI | Target | Source |
|-----|--------|--------|
| Success rate | > 90% | `kanban_token_report.py` |
| Intervention rate | < 10% | Postmortem § Intervention analysis |
| First-pass yield | > 80% | Failure-mode taxonomy |
| Token outliers | Flag at > 2× per-task average | `kanban_token_report.py` |
| Failure-mode concentration | No single category > 30% | Failure-mode taxonomy |
| Autonomous completion | > 80% | Postmortem § Task execution summary |

See README § Agent KPIs for the full 11-metric table with descriptions.

## Six Sigma DMAIC mapping

The reconciliation checklist follows the Define → Measure → Analyze → Improve → Control cycle. A Six Sigma black belt will recognize:

| DMAIC Phase | Reconciliation step | What it covers |
|-------------|-------------------|----------------|
| **Define** | Scope the reconciliation | What plan, what baseline, what success looked like |
| **Measure** | Steps 1–2 | File compliance (git diff), token burn report, failure-mode taxonomy |
| **Measure** | Step 4 | Non-kanban overhead tally (env fixes, manual interventions, plan hardening) |
| **Analyze** | Step 3 | Failure-mode taxonomy — categorize by root cause, flag categories >30%, identify token outliers >2× average |
| **Improve** | Steps 5–6 | Codify lessons into skills, document new pitfalls, sync publishable copies; **promote `.hermes/docs/kanban-*` handoffs into the in-flight index** |
| **Control** | Step 7 | Archive board, remove wave crons + optional monitor cron, verify no orphaned processes; run `handoff-regression-checklist.md` |

See the wiki page `six-sigma-mapping.md` for the full DMAIC mapping including the CTQ tree, defect metrics (DPMO, first-pass yield, process capability), and the belt model.

## Reconciliation checklist

### 1. File-level plan compliance
```bash
git diff --stat <Audit-baseline-sha>..HEAD
python3 hermes-kanban-advanced-workflow/scripts/final_audit_sanity.py --plan-id <plan_id> --tier 1
```

Every file in the plan must show > 0 lines changed vs the audit baseline **or** be cleared by **E001 prior-commit rule**: a done card's `Commit:` line matches an earlier commit that touched that card's full `Files:` list (`find_prior_commit` — same helper as eval-chain step 1). Tier 1 applies this automatically; do **not** create a follow-up card for zero-diff paths that E001 already ALLOWed unless `final_audit_sanity.py` still reports `plan_file_zero_diff`.

**If reconciliation shows zero-diff but workers had E001 ALLOW:** load `plugin/data/references/final-audit-sanity-check.md` § Tier 1 ↔ in-flight — usually missing `Commit:` or path not on card `Files:`.

**If Tier 1 reports other violations:** `--spawn-remediation` per `kanban-advanced:kanban-orchestrator` § Final audit — do not hand-fix from reconciliation.

### 2. Token burn report
```bash
python scripts/kanban_token_report.py --plan <plan_id>
```
Flag any task that burned > 2× the plan average. Include token totals in the KPI report artifact at `.hermes/kanban/reports/`.

> **Fallback:** When `tokens.jsonl` is not configured (no `token_tracker.py` wiring), extract token data manually from agent logs. See `plugin/data/references/manual-token-extraction.md` for extraction commands, cost estimation, and KPI table templates.

### 3. Failure-mode taxonomy
Group task failures by type:
- Protocol violations (worker didn't signal)
- Agent timeouts (agent ran with no commits)
- Auth errors (pre-flight blocked)
- Crashed runs (OOM, segfault)
- Rate-limit stampedes (429 on same provider)

Classify each blocked task with its canonical error code from `plugin/data/registry/error-codes.yaml`. If any category exceeds 30% of tasks, apply mid-run reconciliation.

### 4. Non-kanban overhead
Count time spent on:
- Environment fixes (auth, binaries, service restarts)
- Manual interventions (direct implementation, stuck-task triage)
- Plan hardening (edge case discovery, gap filling)

### 5. Skill updates
Apply lessons learned to skills. If a pitfall was discovered, document it. If a workflow improvement was validated, codify it.

**Handoff promotion (mandatory when `.hermes/docs/kanban-*` was written this run):**

1. Extract the symptom keyword and layer (L0–L6) from the handoff.
2. Add a row to `plugin/skills/kanban-advanced/references/in-flight-governance-index.md`.
3. Update `kanban-*-governance` pitfall text; sync the index mirror under `plugin/data/references/`.
4. Cross-link `wiki/troubleshooting.md` when subscribers or operators would search there first.

### 6. Publishable sync
If kanban skills or prompts changed, update the publishable versions in the `hermes-kanban-advanced-workflow/` directory. Re-run `provision.sh` and verify with `--check`.

### 7. Board cleanup
```bash
# Archive all done tasks
hermes kanban archive <task_ids>

# Kill tmux watch
tmux kill-session -t kanban-watch

# Remove wave crons (mandatory)
bash hermes-kanban-advanced-workflow/scripts/provision_kanban_crons.sh --remove --plan-id <plan_id>
# Optional walk-away monitor
cronjob(action="remove", job_id="<id>")
```

## Mid-run reconciliation

If failure rate exceeds 30% during execution:
1. Check worker SOUL.md for corruption
2. Verify agent binary works: `bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke`
3. Review card body format — are `Files:` lines present?
4. Check for environment leaks (wrong paths, stale configs)
5. Apply fixes, reset intervention counter, resume

## When reconciliation surfaces a problem (load in order)

| Symptom | First load | Notes |
| --- | --- | --- |
| Zero-diff plan file but E001 ALLOW in-flight | `plugin/data/references/final-audit-sanity-check.md` § Tier 1 ↔ E001 | Fix card `Files:` / `Commit:` before follow-up card |
| `final_audit_sanity.py` exit 1 at reconcile | `final-audit-sanity-check.md` | Remediation loop — not reconciliation's job to skip |
| Missing tier JSON / `uncaught_violation_count: null` in KPI | `kanban-advanced:kanban-postmortem` § Final audit KPIs | Re-run audit before cleanup |
| Failure rate > 30% mid-run | This skill § Mid-run reconciliation | Worker SOUL, smoke, card bodies |
| New recurring symptom | `in-flight-governance-index.md` + `wiki/troubleshooting.md` | Promote row per § Skill updates step 5 |
