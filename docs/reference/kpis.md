# Agent KPIs

Every plan execution produces a reconciliation report and postmortem with these metrics. The agent surfaces KPIs at the reconciliation checkpoint — you don't need to run reports manually.

| KPI                           | What it measures                                                                   | Target                      |
| ----------------------------- | ---------------------------------------------------------------------------------- | --------------------------- |
| **Success rate**              | Completed tasks / total tasks                                                      | > 90%                    |
| **Intervention rate**         | Tasks requiring orchestrator takeover / total tasks                                | < 10%                    |
| **Autonomous completion**     | Tasks completed without human or orchestrator intervention                         | > 80%                    |
| **Token burn (CLI Agent)**    | Total coding-agent tokens consumed                                                 | Per-plan budget             |
| **Token burn (Hermes)**       | Orchestrator + worker tokens (estimated)                                           | Tracked for efficiency      |
| **Cache efficiency**          | Cache read tokens / total input tokens                                             | Higher = cheaper            |
| **Per-task token average**    | Mean tokens per task; outliers flagged at >2× average                           | Flag, investigate           |
| **Wall clock duration**       | Hours from first dispatch to last completion                                       | Plan-dependent              |
| **Completeness violations**   | Acceptance/Call-sites misses caught by worker or orchestrator remediation          | 0 uncaught (sail-through target) |
| **final_audit_rounds**        | Post-flight remediation rounds (`Audit-round` on audit card)                       | ≤ `final_audit_max_remediation_rounds` (default 2) |
| **plan_scope_gaps**           | Tier 1 violations from `{plan_id}_audit_tier1.json`                                | 0 at cleanup |
| **doc_coverage_gaps**         | Tier 2 violations from `{plan_id}_audit_tier2.json`                                | 0 at cleanup |
| **uncaught_violation_count**  | Gaps that reached cleanup without remediation; **`null`** when tier JSON absent    | 0 (not `null`) |
| **parser_miss_count**           | Tier 1/2 heuristic false positives excluded from uncaught count                    | 0 |
| **thrash_outliers**             | Tasks with `reblock_count ≥ 3` in `{plan_id}_kpi.json` (objects: `task_id`, `reblock_count`, `event_count`) | 0 |
| **auth_escalation_count**     | Tasks classified `auth_error` in failure taxonomy                                  | 0 |
| **token_tracker_available**     | Whether `token_tracker.py` was reachable at postmortem generation                  | `true` when token logging expected |
| **KPI artifact**              | `{plan_id}_kpi.json` + `kpi_history.jsonl` from `generate_postmortem.py`         | Trend across plans          |
| **Failure-mode distribution** | Count by category: protocol violation, timeout, auth, crash, evaluation chain deny | No single category > 30% |
| **First-pass yield**          | Tasks completed on first dispatch attempt (no retries)                             | > 80%                    |
| **Non-kanban overhead**       | Time spent on env fixes, manual interventions, plan hardening                      | Minimize                    |
