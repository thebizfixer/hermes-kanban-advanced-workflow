# Error Codes

Canonical registry: `plugin/data/registry/error-codes.yaml` (bundled with the plugin).

## Full listing

| Code      | Severity      | Description                                   | Retry |
| --------- | ------------- | --------------------------------------------- | ----- |
| E001      | error         | File not in diff (allows `already_committed` when prior SHA matches message + diff-tree) | Yes   |
| E002      | warning       | Unlisted file change (auto-reverted)          | No    |
| E003      | error         | Test failure (tsc errors filtered to card Files scope; pre-existing out-of-scope errors do not block) | Yes   |
| E004      | error         | Commit message mismatch                       | No    |
| E005      | warning       | Token log missing (superseded by E018)        | No    |
| E006      | error         | Zero output                                   | Yes   |
| E007      | error         | Disk full                                     | No    |
| E008      | error         | Network down                                  | Yes   |
| E009      | error         | Push to integration branch                    | No    |
| E010      | error         | Forbidden command (sudo/rm)                   | No    |
| E011      | error         | Cross-mount filesystem                        | No    |
| E012      | warning       | Stale preflight cache                         | No    |
| E013      | error         | Evaluation chain missing                      | No    |
| E014      | error         | Orchestrator-only on worker; verification Files:/agent contradiction; verification-deploy on worker | No    |
| E015      | error         | Test environment invalid                      | Yes   |
| E016      | error         | Commit not reachable from staging             | No    |
| E017      | error         | Excessive churn (>3× line budget)             | No    |
| E018      | error         | Token entry not exact (replaces E005)         | No    |
| E019      | error         | Destructive git op (reset --hard / theirs)    | Yes   |
| E020      | error         | Agent output unparseable / missing usage      | Yes   |
| E021      | error         | Worktree incomplete (missing kanban scripts)  | No    |
| E022      | error         | Parallel subagent gate domain timeout           | Yes   |
| E023      | error         | Repeated identical error at same commit (lattice memory; invalidated when HEAD advances) | No    |
| E028      | error         | Layout/presentation acceptance failed           | Yes   |
| E029      | error         | Presentation a11y acceptance failed             | Yes   |
| P001-P009 | error/warning | Card body policy violations                   | No    |
| A001-A003 | error         | Attestation missing/stale/tampered            | No    |
| PR001     | error         | Profile no config                             | No    |
| G001-G003 | error         | Gateway down / dispatcher wedged / goal-card  | No    |

## Recovery

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --list
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py <task_id> <code>
```

Categories: attestation (A*), policy (P*), evaluation chain (E*), preflight (E011, PR001, …), board validation.

**Full recovery narratives:** [wiki/troubleshooting.md](../../wiki/troubleshooting.md). **In-flight symptom router:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` or [handoff-regression-checklist.md](../../plugin/data/references/handoff-regression-checklist.md).
