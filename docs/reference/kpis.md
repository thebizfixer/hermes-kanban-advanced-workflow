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
| **Failure-mode distribution** | Count by category: protocol violation, timeout, auth, crash, evaluation chain deny | No single category > 30% |
| **First-pass yield**          | Tasks completed on first dispatch attempt (no retries)                             | > 80%                    |
| **Non-kanban overhead**       | Time spent on env fixes, manual interventions, plan hardening                      | Minimize                    |
