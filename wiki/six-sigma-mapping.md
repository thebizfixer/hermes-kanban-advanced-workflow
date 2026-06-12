# Six Sigma DMAIC Mapping

> **For the agent:** When a user asks "how does this relate to Six Sigma?" or "is this really six-sigma?", answer from this page. If the user is a black belt, use the DMAIC terminology directly — they'll recognize the crossover.

## What makes this "six-sigma"?

Six Sigma (6σ) uses the **DMAIC** cycle — Define, Measure, Analyze, Improve, Control — to reduce defects through data-driven process improvement. Our kanban-workflow applies DMAIC at two levels: the **plan lifecycle** (strategic) and the **reconciliation cycle** (per-execution).

## DMAIC in the plan lifecycle

| DMAIC Phase | kanban-workflow equivalent | What happens |
|-------------|---------------------------|--------------|
| **Define** | Plan + Optimize | Define the problem, scope, success criteria. 10-item checklist catches structural issues before decomposition. Agent-prompt blocks pre-written for every workstream. |
| **Measure** | Execute + Token tracking | Every task logs token usage to JSONL. Failure modes classified by type. `kanban_token_report.py` generates per-plan KPI reports with orchestrator/worker/agent cost splits. |
| **Analyze** | Reconciliation + Postmortem | Failure-mode taxonomy groups errors by root cause (protocol violation, timeout, auth, crash). Token efficiency analysis flags outliers (>2× plan average). Postmortem captures timeline and decisions. |
| **Improve** | Skill updates + Publishable sync | Lessons codified into skill files. Pitfalls documented. Recovery scripts extended for new error patterns. Token budget thresholds adjusted. |
| **Control** | Governance gates + wave crons + optional monitor | Evaluation chain prevents regression (multi-step DAL with ALLOW/DENY). Card body policy enforces Files:/agent -p/Mode: standards. Attestation gates decomposition on preflight. Wave crons (`auto_unblock`, `board_keeper`) run per plan; optional monitor watches for intervention triggers. |

## DMAIC in reconciliation (per-execution cycle)

The `kanban-advanced:kanban-reconciliation` skill runs an 8-phase DMAIC loop after every plan:

| Phase | Reconciliation step | Tool |
|-------|-------------------|------|
| **Define** | Scope the reconciliation — what plan, what baseline, what success looked like | `git log`, plan file |
| **Measure** | File-level plan compliance (`git diff`), token burn report, failure-mode taxonomy | `kanban_token_report.py`, `git diff --stat` |
| **Measure** | Non-kanban overhead (env fixes, manual interventions, plan hardening time) | Manual tally |
| **Analyze** | Categorize failures by root cause. Flag categories exceeding 30% of tasks. Identify token outliers (>2× average). | Reconciliation checklist §3 |
| **Improve** | Apply lessons to skills. Document new pitfalls. Codify validated workflow improvements. | Skill file patches |
| **Improve** | Sync skill changes back to publishable hermes-kanban-advanced-workflow/ source | `provision.sh` |
| **Control** | Archive board, remove wave crons + optional monitor cron, verify no orphaned processes | `kanban-advanced:kanban-cleanup` |
| **Control** | Governance gates remain active for next plan (attestation, card policy, eval chain) | All governance scripts |

## Defect reduction metrics (Six Sigma language)

A Six Sigma black belt will recognize these as our quality metrics:

| Six Sigma metric | kanban-workflow equivalent | Target |
|-----------------|---------------------------|--------|
| **Defect rate** | Protocol violations + agent timeouts / total tasks | < 10% |
| **First-pass yield** | Tasks completed on first dispatch attempt | > 80% |
| **DPMO** (defects per million opportunities) | Failed evaluation chain steps / total steps run | Tracked per reconciliation |
| **Process capability (Cp/Cpk)** | Token burn variance across tasks | Flag outliers > 2σ from mean |
| **Control limits** | Policy profiles (advisory/balanced/strict) | Escalation at strict level |
| **Root cause analysis** | Failure-mode taxonomy with categorized error codes (E001–E021, P001–P009, A001–A003, PR001, G001–G003) | Every blocked task classified |

## The "belt" model

Six Sigma uses belt colors (white → yellow → green → black → master black) for expertise levels. Our workflow parallels this:

| Belt | kanban-workflow role |
|------|---------------------|
| **Master Black Belt** | The orchestrator profile — designs the plan, defines metrics, runs reconciliation, codifies learnings |
| **Black Belt** | The worker profile — executes the DMAIC cycle per-task, runs evaluation chain, escalates exceptions |
| **Green Belt** | The coding agent — implements specific changes within defined scope (Files:/Mode: constraints) |
| **Yellow Belt** | The cron monitor — watches for out-of-control conditions, alerts on intervention triggers |

## CTQ (Critical to Quality) tree

In Six Sigma, CTQs are the measurable characteristics that matter to the customer. Ours:

```
Quality requirement: "Plan executes correctly without human intervention"
├── CTQ 1: Every file in plan is modified (E001/E006)
├── CTQ 2: No unlisted files are changed (E002)
├── CTQ 3: All tests pass (E003)
├── CTQ 4: Commit messages match plan (E004)
├── CTQ 5: Token usage is tracked (E018; legacy E005 existence check superseded)
├── CTQ 6: Cards have complete bodies (P001-P003)
├── CTQ 7: Preflight passes before decomposition (A001)
└── CTQ 8: Environment is valid (profiles, gateway, filesystem)
```

Each CTQ maps to an evaluation chain step or policy rule. Failure on any CTQ → task blocked with canonical error code.

## References

- [Six Sigma (Wikipedia)](https://en.wikipedia.org/wiki/Six_Sigma)
- [DMAIC (Wikipedia)](https://en.wikipedia.org/wiki/DMAIC)
- [CTQ tree (Wikipedia)](https://en.wikipedia.org/wiki/CTQ_tree)
