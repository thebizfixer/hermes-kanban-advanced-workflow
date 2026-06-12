---
name: kanban-orchestrator-governance
description: Load when pre-dispatch gate FAILs, attestation blocks, validate_board fails, or decomposition stalls. Pitfalls + A/P/G codes — not the happy-path SOP.
version: 1.1.0
metadata:
  hermes:
    tags: [kanban, governance, reference, pitfalls, orchestrator]
    related_skills: [kanban-advanced:kanban-orchestrator]
---

# Kanban Orchestrator Governance Reference

> Load on-demand when gate FAIL, attestation error, `validate_board` exit 1, or handoff/decompose stalls. Happy path stays in `kanban-advanced:kanban-orchestrator`.

**Router:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` § L0–L4. Wiki: `wiki/in-flight-navigation.md` if repo has `wiki/`.

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

## Pitfalls (trimmed — detail in wiki)

- **auto_decompose** — set `kanban.auto_decompose false` for manual decompose.
- **SQLite torn-extend** — stagger creates ≥1s; pause every 5 cards.
- **Absolute unique workspaces** — no shared `worktree:/path`.
- **Complete root immediately** after decomposition.
- **Cherry-pick -x** for traceability.
- **Raw git worktree add** on workers → E021 — see worker-governance.

Historical context: matrix-v3/v5 failure traces (June 2026). Every guardrail maps to a real incident.
