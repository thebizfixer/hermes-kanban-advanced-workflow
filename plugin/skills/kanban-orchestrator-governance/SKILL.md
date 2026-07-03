---
name: kanban-orchestrator-governance
description: Load when pre-dispatch gate FAILs, attestation blocks, validate_board fails, or decomposition stalls. Pitfalls + A/P/G codes — not the happy-path SOP.
version: 1.2.0
metadata:
  hermes:
    tags: [kanban, governance, reference, pitfalls, orchestrator]
    related_skills: [kanban-advanced:kanban-orchestrator]
---

# Kanban Orchestrator Governance Reference

> Load on-demand when gate FAIL, attestation error, `validate_board` exit 1, handoff/decompose stalls, **or final audit exit 2 / remediation loop / check 13**. Happy path stays in `kanban-advanced:kanban-orchestrator`.

**Router:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` § L0–L4 **and L7 (final audit)**. Wiki: `wiki/in-flight-navigation.md` if repo has `wiki/`.

**Constitution (MUST / MUST NOT):**

- MUST NOT complete gate until `validate_board.sh` passes and crons verified.
- MUST NOT override `pre_dispatch_gate.sh` or attestation exit codes.
- MUST NOT complete worker cards without evaluation chain (orchestrator manual complete = G14 violation).
- MUST use `--gate-id` when gate already exists — no duplicate gates.
- MUST prefer `--cards-yaml` when memory YAML exists.
- Auth / `.worktreeinclude` / cross-mount → T3 operator.

## Pre-dispatch gate checks (compact)

Detail: `wiki/governance.md` § Layer 2. Run: `bash <BUNDLE>/scripts/pre_dispatch_gate.sh <plan_id>`.

| Check | FAIL/WARN |
|-------|-----------|
| plan on `${working_branch}` | FAIL |
| plan pushed | WARN |
| preflight | WARN |
| coding_agent_cli | FAIL |
| attestation | FAIL |
| card_policy_script | WARN |
| plan_memory | FAIL |
| kanban_db | FAIL |
| cron_scripts | FAIL |
| cron_hermes_path | FAIL |
| gateway_running | WARN |

## Parallel subagent gate (E022)

Default orchestrator path when `subagent_gate.enabled` is not `false` and `delegate_task` / `delegation` is available. Serial fallback: `pre_dispatch_gate.sh`.

| Symptom | Tier | Recovery |
|---------|------|----------|
| Subagent timeout (plan/env/infra) | T2 | E022 — note domain; run serial `pre_dispatch_gate.sh` |
| Malformed subagent JSON | T2 | Serial fallback |
| `delegation` toolset missing | T1 | Serial fallback (parallel default needs delegation) |
| Parallel pass but serial fail | T3 | Investigate skipped check — prefer serial until resolved |
| Force serial only | T1 | `subagent_gate.enabled: false` in overlay |

Detail: `plugin/data/references/parallel-subagent-gate.md`. Config: `wiki/configuration.md` § `subagent_gate`.

## Attestation A001–A003

| Code | Tier | Recovery |
|------|------|----------|
| A001 | T2 | Run preflight + `kanban_attestation.py` before decompose |
| A002 | T2 | Re-attest (>120 min TTL) |
| A003 | T3 | Discard file; investigate tamper; re-attest |

## Card policy P001–P009

| Code | Tier | Recovery |
|------|------|----------|
| P001 | T2 | Add `Files:` line |
| P002 | T2 | Add `agent -p` fenced block |
| P003 | T2 | Add `Mode:` line |
| P004 | T3 | Human review or split card |
| P005 | T2 | Remove `--model` from card body |
| P006 | T2 | Recreate with worktree workspace |
| P007 | T2 | Unique `/tmp/wt-*` per card |
| P008 | T2 | Use `kanban link` not `--parents` |
| P009 | T2 | Split card (35-turn budget) |

## Gateway / profile G001–G003, PR001

| Code | Tier | Recovery |
|------|------|----------|
| G001 | T3 | `hermes gateway run` |
| G002 | T3 | Restart gateway; check dispatcher |
| G003 | T2 | Fix goal cards / `verify_goal_cards.py` |
| PR001 | T3 | Copy profile `config.yaml` from default |

## kanban_recover.py (MBB)

```bash
python3 scripts/kanban_recover.py --list
python3 scripts/kanban_recover.py --cascade <plan_id>   # pause / resume board
```

## Salvage

Iteration-limit cards: check worktree commits before re-dispatch. Full flow: `plugin/data/references/salvage-pattern-iteration-exhausted-cards.md`.

## Diagnostic output

When pre-dispatch gates, attestation, verify-skills, or postmortem tools emit
diagnostics, summarize — never paste raw output. Format: what's wrong → what
it means → what to do. Full pattern: `kanban-advanced:kanban-reconciliation` §
Diagnostic summarization.

## Pitfalls (trimmed — detail in wiki)

- **auto_decompose** — set `kanban.auto_decompose false` for manual decompose.
- **SQLite torn-extend** — stagger creates ≥1s; pause every 5 cards.
- **Absolute unique workspaces** — no shared `worktree:/path`.
- **Complete root immediately** after decomposition.
- **Cherry-pick -x** for traceability.
- **Raw git worktree add** on workers → E021 — see worker-governance.

Historical context: matrix-v3/v5 failure traces (June 2026). Every guardrail maps to a real incident.

## Final audit / post-flight (L7)

Load **`plugin/data/references/final-audit-sanity-check.md`** first for any post-flight symptom. Index § L7 has command rows.

| Symptom | Tier | Recovery |
| --- | --- | --- |
| `final_audit_sanity.py` exit **2** | T2/T3 | Fix plan path, git, DB; `kanban_block` audit — no remediation spawn |
| exit **1** violations | T2 | `--spawn-remediation`; wait; re-run `--tier all` |
| Max rounds / audit blocked | T2/T3 | Review tier JSON; operator; `final_audit_max_remediation_rounds` |
| `gave_up` remediation | T3 | Escalation on audit card; tier JSON `escalated` |
| `plan_file_zero_diff` after E001 ALLOW | T2 | Add path to card `Files:`; stamp `Commit:`; see § Tier 1 ↔ E001 |
| Tier 2 false positive | T2 | `final_audit_overrides` in overlay (`wiki/configuration.md`) |
| check **13** FAIL | T2 | Close/archive remediation children; `validate_board.sh` |
| Premature audit promote | T2 | Do not run `auto_unblock` manually — `_has_active_remediation_children` |

## Walk-away mode: false — Hard Stop

When `walk_away_mode: false` in config:
- After final audit: checkpoint + STOP
- Do NOT archive, cleanup, or run postmortem
- These actions are operator-driven via default profile
- Silently finishing or skipping checkpoints without walk-away mode is a governance violation (orchestrator skill line 252)
