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

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `sentimentary-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
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
| **Improve** | Steps 5–6 | Codify lessons into skills, document new pitfalls, sync publishable copies |
| **Control** | Step 7 | Archive board, remove monitoring cron, verify no orphaned processes |

See the wiki page `six-sigma-mapping.md` for the full DMAIC mapping including the CTQ tree, defect metrics (DPMO, first-pass yield, process capability), and the belt model.

## Reconciliation checklist

### 1. File-level plan compliance
```bash
git diff --stat <pre-plan-baseline>..HEAD
```
Every file in the plan must show > 0 lines changed. Zero-diff = dropped sub-task → create follow-up card.

### 2. Token burn report
```bash
python scripts/kanban_token_report.py --plan <plan_id>
```
Flag any task that burned > 2× the plan average. Include token totals in the KPI report artifact at `.hermes/kanban/reports/`.

> **Fallback:** When `tokens.jsonl` is not configured (no `token_tracker.py` wiring), extract token data manually from agent logs. See `references/manual-token-extraction.md` for extraction commands, cost estimation, and KPI table templates.

### 3. Failure-mode taxonomy
Group task failures by type:
- Protocol violations (worker didn't signal)
- Agent timeouts (agent ran with no commits)
- Auth errors (pre-flight blocked)
- Crashed runs (OOM, segfault)
- Rate-limit stampedes (429 on same provider)

Classify each blocked task with its canonical error code from `hermes-kanban-advanced-workflow/registry/error-codes.yaml`. If any category exceeds 30% of tasks, apply mid-run reconciliation.

### 4. Non-kanban overhead
Count time spent on:
- Environment fixes (auth, binaries, service restarts)
- Manual interventions (direct implementation, stuck-task triage)
- Plan hardening (edge case discovery, gap filling)

### 5. Skill updates
Apply lessons learned to skills. If a pitfall was discovered, document it. If a workflow improvement was validated, codify it.

### 6. Publishable sync
If kanban skills or prompts changed, update the publishable versions in the `hermes-kanban-advanced-workflow/` directory. Re-run `provision.sh` and verify with `--check`.

### 7. Board cleanup
```bash
# Archive all done tasks
hermes kanban archive <task_ids>

# Kill tmux watch
tmux kill-session -t kanban-watch

# Remove monitoring cron if present
cronjob(action="remove", job_id="<id>")
```

## Mid-run reconciliation

If failure rate exceeds 30% during execution:
1. Check worker SOUL.md for corruption
2. Verify agent binary works: `agent -p "echo ok" --output-format json`
3. Review card body format — are `Files:` lines present?
4. Check for environment leaks (wrong paths, stale configs)
5. Apply fixes, reset intervention counter, resume
