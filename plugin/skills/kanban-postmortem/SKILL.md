---
name: kanban-postmortem
description: Structured plan retrospective — eight-section report for the operator's agent to digest before the next plan.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, postmortem, retrospective, learning, walk-away]
    related_skills: [kanban-advanced:kanban-cleanup, kanban-advanced:kanban-notify, kanban-advanced:kanban-reconciliation, kanban-advanced:kanban-planning]
---

# Kanban Postmortem — Plan Retrospective

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

The postmortem is the **final learning artifact** of a kanban plan run. It is written for the **operator's Hermes agent** (not the orchestrator mid-run): read sections 5–8 before drafting the next plan, and feed section 6 into skill updates when a pitfall repeats across runs.

**Generator:** `hermes-kanban-advanced-workflow/scripts/generate_postmortem.py` — SSOT for section headings, metrics, and failure classification.

**When:** `kanban-advanced:kanban-cleanup` Step 0 — generate while token logs, SQLite task history, and intervention counters are still intact; archive the board only after the report file exists.

## Generate the report

```bash
PLAN_ID="${HERMES_KANBAN_PLAN_ID:-<plan-id>}"
python hermes-kanban-advanced-workflow/scripts/generate_postmortem.py \
  --plan-id "$PLAN_ID" \
  --output .hermes/kanban/reports/
```

Confirm stdout: `Postmortem written: ...` and that the file contains all eight `## N.` section headings (the script exits non-zero if any are missing).

Also writes **`{plan_id}_kpi.json`** beside the markdown report and appends the same payload to **`kpi_history.jsonl`** for cross-run trending. Merges cross-plan lessons into `.hermes/kanban/memory/_global.json` when KPI completeness or subsystem failures warrant it (`scripts/lib/cross_plan_memory.py`).

### Sail-through acceptance (next-run targets)

Encoded in KPI `completeness` and postmortem heuristics:

| Target | KPI field |
|--------|-----------|
| 0 uncaught false completions | `completeness.uncaught_violation_count` (goal 0; **`null`** when tier1/tier2 audit JSON is missing — not a pass) |
| Violations recorded + remediated when caught | `completeness.remediation_cards_issued`, worker vs orchestrator catch counts |
| Wall clock ≤ 1.5× effective estimate | `wall_clock_hours` vs plan turn-estimates |
| 0 manual git interventions | postmortem §5 pitfalls + `kanban-git` skill adherence |
| 0 OAuth-stampede blocks | `auth_escalation_count`, `subsystem_failures.auth_error` |

### CLI flags (cross-reference `generate_postmortem.py`)

| Flag | Default | Purpose |
| --- | --- | --- |
| `--plan-id` | *(required)* | Matches `plan_id:` first line in card bodies and token log entries |
| `--output` | `~/.hermes/kanban/reports/` | Directory or explicit `.md` path; directory → `{plan_id}_postmortem_{YYYY-MM-DD}.md` |
| `--token-log` | `KANBAN_TOKEN_LOG` or `~/.hermes/kanban/tokens.jsonl` | Override worker token JSONL |
| `--db` | `KANBAN_DB` or `~/.hermes/state.db` | Override Hermes kanban SQLite DB |
| `--interventions` | `~/.hermes/kanban/logs/interventions.count` | Override intervention counter file |
| `--stdout` | off | Print full markdown to stdout after writing the file |

### Data sources

| Source | Env override | Feeds sections |
| --- | --- | --- |
| Token JSONL | `KANBAN_TOKEN_LOG` | 2, 7; pitfall heuristics in 5 |
| Kanban SQLite | `KANBAN_DB` | 1, 2, 3 |
| `interventions.count` | `KANBAN_INTERVENTIONS` | 1, 4 |
| `interventions.jsonl` | `~/.hermes/kanban/logs/` | 4 (structured rows from `kanban-advanced:kanban-notify`) |

Missing DB or token log produces **data notes** at the top of the report; the generator still emits all eight sections with best-effort inference.

## Final audit KPIs (§2 Agent Performance subsection)

When tier JSON exists, the markdown report includes **### Final audit** under Agent Performance with rounds, tier1/tier2 gap counts, and uncaught violations.

| Symptom in KPI / report | Meaning | Load |
| --- | --- | --- |
| `uncaught_violation_count: null` | Tier JSON missing — **unknown**, not a pass | Re-run `final_audit_sanity.py` before archive; `final-audit-sanity-check.md` |
| `uncaught_violation_count > 0` | Gaps reached cleanup without matching remediation | `kanban-orchestrator` § Final audit; tier JSON paths |
| `parser_miss_count > 0` | Tier1/2 heuristic false positives (acceptance/call-site/doc coverage) — excluded from uncaught | `final-audit-sanity-check.md` § heuristic limits |
| `wall_clock_hours` | Capped at final audit completion when all impl cards terminal (not postmortem generation time) | Compare to plan estimates |
| `final_audit_rounds` high vs overlay max | Remediation loop ran many times | `wiki/configuration.md`; operator triage |
| WARN in `audit_tier_notes` | Missing `{plan_id}_audit_tier1.json` or tier2 | Re-run audit with default JSON writes |

**Do not** archive the board or treat the plan as sail-through when uncaught is `null` and audit never ran.

## Report structure (eight sections)

Section titles and order are fixed — do not rename or reorder when editing generated output.

### 1. Execution Summary

**Purpose:** One-screen plan outcome for the next planning session.

**Includes:**

- Plan id, generation timestamp
- Task totals: completed, failed/blocked, autonomous completions (completed minus orchestrator takeovers)
- Success rate (%), intervention count and rate (%)
- Wall-clock hours (from task/event timestamps when available)

**Agent use:** Compare success and intervention rates to prior postmortems; if intervention rate > 30%, require sad-path and preflight updates in the next plan.

### 2. Agent Performance

**Purpose:** Per-task accountability — who ran, how long, how many tokens.

**Includes:**

- Table from kanban DB: task id, status, profile, failure modes, event count
- Table from token log: task id, model, formatted token total, duration, run status

**Agent use:** Identify hot tasks (>2× average tokens in section 7) and profiles with repeated `blocked` / `crashed` status; split or re-scope cards in the next decomposition.

### 3. Failure Taxonomy

**Purpose:** Classify *why* tasks failed so the next plan's sad-path table is grounded in evidence.

**Canonical modes** (from `generate_postmortem.py` `FAILURE_KINDS`):

| Mode | Meaning |
| --- | --- |
| `protocol_violation` | Worker exited without `kanban_complete` or completion note implies protocol breach |
| `reclaimed` | Dispatcher reclaimed idle worker |
| `timed_out` | Task or agent exceeded time budget |
| `crashed` | Agent OOM, segfault, or hard crash |
| `gave_up` | Worker abandoned after retries |
| `blocked` | Task blocked on dependency or error |
| `iteration_budget` | Same-file / scope iteration exhausted |
| `ghost_task` | No live process for an active card |
| `auth_error` | Auth/session failure |
| `orchestrator_takeover` | Orchestrator implemented instead of worker |

**Includes:** Count and task id list per mode.

**Agent use:** Copy dominant modes into the next plan's **Sad-Path Contingencies** table with mitigations and auto-retry flags.

### 4. Intervention Log

**Purpose:** Record every operator touch during walk-away — feeds walk-away KPI and trust metrics.

**Includes:**

- Persistent counter from `interventions.count`
- Rate vs total tasks
- JSONL table: timestamp, task id, reason (when `kanban-advanced:kanban-notify` appended rows)

**Agent use:** If counter-only (no JSONL), tighten notify persistence in `kanban-advanced:kanban-notify` § Persistence. High intervention rate without JSONL detail → add explicit logging to the next run.

### 5. Discovered Pitfalls

**Purpose:** Actionable patterns the **next plan author** must address — not generic advice.

**Generator heuristics (examples):**

- Protocol violations → enforce board signal on every success path
- Reclaim/timeout pattern → heartbeats + terminal commands for long runs
- Iteration budget → split same-file cards (>200 lines)
- Intervention rate > 30% → mid-run reconciliation before resume
- Token burn > 2× plan average → name hot task ids

**Agent use:** Turn each bullet into a sad-path row or plan optimization checklist item before decomposition.

### 6. Skill Updates Needed

**Purpose:** Map pitfalls to **kanban skill** changes (worker, orchestrator, reconciliation, notify).

**Generator maps pitfalls to recommendations** (e.g. protocol → `kanban-advanced:kanban-worker`, intervention rate → `kanban-advanced:kanban-orchestrator`). When no signature matches, the section states that explicitly.

**Agent use:** After the operator approves, apply edits to `hermes-kanban-advanced-workflow/skills/` and sync publishable copies per `kanban-advanced:kanban-reconciliation` § Publishable sync. Do not block the next plan on skill PRs — track follow-up cards if needed.

### 7. Token Economics

**Purpose:** Cost awareness for line-budget and card granularity decisions.

**Includes:**

- Cursor tokens (logged), Hermes tokens (logged), combined total
- Per-task average (Cursor)
- Cache read ratio when cache fields present
- High-burn tasks (>2× average)

**Agent use:** Feed totals into plan optimization **line budget**; split cards that drove >2× average burn.

### 8. Learning Summary

**Purpose:** Three-to-five bullets the operator's agent reads **first** when returning after walk-away.

**Includes:**

- Success and intervention rate recap
- Dominant failure mode (or "none detected")
- Logged Cursor spend reminder
- Explicit instruction: read sections 5–6 before writing the next plan; update skills when pitfalls repeat

**Agent use:** Paste distilled bullets into the next plan's frontmatter or a "Prior run learnings" subsection; link the postmortem file path.

## DMAIC Improve loop (handoff → index)

When execution surfaces a **new** recurring failure (including forensic notes in project `.hermes/docs/kanban-*` handoffs):

1. **Add** a symptom row to `plugin/skills/kanban-advanced/references/in-flight-governance-index.md` (Trigger | Layer | Tier | First command | Verify).
2. **Patch** the matching governance skill pitfall (`kanban-worker-governance` or `kanban-orchestrator-governance`).
3. **Anchor** `wiki/troubleshooting.md` if the failure is operator-visible.
4. **Pointer** — if the SSOT path changed, update the stub at `plugin/data/references/in-flight-governance-index.md` (do not duplicate the full index there).
5. **Run** `plugin/data/references/handoff-regression-checklist.md` before the next decomposition on the same project.

If an error code accounts for >30% of blocked tasks in this postmortem, promote it to an embedded quick row in the governance skill (not only the index).

## Consumption workflow (before the next plan)

1. **Locate** the latest report: `.hermes/kanban/reports/{plan_id}_postmortem_*.md`
2. **Read** §8 Learning Summary, then §5 Discovered Pitfalls and §6 Skill Updates Needed
3. **Update** the upcoming plan: sad-path table, same-file serialization, line budget flags
4. **Optional:** Compare §1 metrics to `kanban-advanced:kanban-reconciliation` KPI template for trend arrows across plans
5. **Do not delete** postmortem files — they are the audit trail (`kanban-advanced:kanban-cleanup` § What NOT to clean up)

## Manual enrichment

The generator is deterministic from logs. The orchestrator or operator agent may **append** a short "Operator notes" subsection after generation (reconciliation decisions, dropped sub-tasks, CI build ids) — do not remove or renumber the eight canonical sections.

## Pitfalls

- **Archiving before postmortem.** Task rows disappear from active views; token log may still exist but failure taxonomy degrades.
- **Missing `plan_id` on cards.** Generator matches tasks via body `plan_id:` line — every card body must include it.
- **Skipping intervention JSONL.** Counter-only §4 loses *why* interventions happened.
- **Treating postmortem as KPI.** Reconciliation KPI is a separate artifact; postmortem is learning-focused and consumed by the planning agent.
- **Ignoring §6 when pitfalls repeat.** Same pitfall on two runs → mandatory skill patch or plan structural change.

## Cross-references

- Generator implementation: `hermes-kanban-advanced-workflow/scripts/generate_postmortem.py` (`SECTION_TITLES`, `build_report`, `parse_args`)
- Cleanup ordering: `kanban-advanced:kanban-cleanup` § Step 0
- Intervention logging: `kanban-advanced:kanban-notify` § Persistence (postmortem input)
- Plan optimization gate: `kanban-advanced:kanban-planning` § Plan Optimization
- Reconciliation overlap: `kanban-advanced:kanban-reconciliation` (mid-run vs post-plan; postmortem supersedes informal notes for learning)
