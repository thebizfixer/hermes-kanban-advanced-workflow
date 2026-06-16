# In-flight navigation

> **For the agent:** Three-tier sad-path routing. Happy path = SOUL + procedural skills only. On first rail → governance skill + [in-flight index](../plugin/skills/kanban-advanced/references/in-flight-governance-index.md). Deep matrices → this wiki.

## Three-step router (all roles)

1. **Hit a rail** (DENY, gate FAIL, block reason with code/tag).
2. **Load Tier 2:** `skill_view("kanban-advanced:kanban-*-governance")` then `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")`.
3. **Tier 3 only if novel:** `wiki/governance.md`, `wiki/troubleshooting.md`, or `plugin/data/references/*.md`.

Project `.hermes/docs/kanban-*` handoffs are **historical** — not in worktrees. Recurring symptoms belong in the plugin index.

## Belt × layer map

| DMAIC | Belt | Layers | Runtime doc | Sad-path first load |
|-------|------|--------|-------------|---------------------|
| Define | MBB | L0 | `kanban-planning` | Index L0 |
| Control (pre) | MBB | L1–L2 | preflight, attestation, gate | Index L1–L2 |
| Control (handoff) | MBB / chat | L3 | `kanban_handoff.py` | Index L3, [[decomposition-workflow]] |
| Control (structure) | MBB | L4 | orchestrator standard process | Index L4 |
| Measure | BB | L5–L6 | `kanban-worker` Steps 3–6 | worker-governance + index |
| Analyze | MBB | Reconcile | `kanban-reconciliation` | [[six-sigma-mapping]] |
| Improve | MBB | Docs | `kanban-postmortem` | Index row + governance pitfall |
| Control (runtime) | Yellow | crons | `auto_unblock`, `board_keeper` | [[governance]] § Auto-progression |

## Worktree vs runtime access

| What | MBB (project root) | BB (card worktree) | Path |
|------|-------------------|-------------------|------|
| Skills / SOUL | Profile home | Same — not in WT | `skill_view("kanban-advanced:…")` |
| Scripts | `$HERMES_HOME/scripts/` or bundle | `.hermes/scripts/` if E021 passed | Index bundle resolution |
| `wiki/` | Yes if repo commits it | **Often missing** | Index + governance skills first |
| Plan file | Main repo | `git checkout origin/${working_branch} -- <plan>` | Worker orient |
| `.env`, venv | Main repo | Only if `.worktreeinclude` | `plugin/data/references/operator-provisioning.md` (T3) |

## Orchestrator router (MBB — board / decompose)

| Symptom | Layer | Tier | Index keywords | Deep dive |
|---------|-------|------|----------------|-----------|
| Gate / attestation / preflight fail | L1–L2 | T2 | preflight, gate FAIL, A00x | in-flight index L1–L2 |
| Handoff stuck / exit 2–4 | L3 | T2/T3 | handoff ready, exit | `decomposition-workflow.md` |
| Scratch cards / bad decompose | L4 | T2 | scratch, cards-yaml | in-flight index L4 |
| Crons / validate fail | L4 | T2 | crons missing, validate_board | `wiki/governance.md` § crons |
| Salvage / iteration limit | L6 | T2 | iteration limit, E001 | salvage reference |
| Final audit exit-2 / max rounds / remediation stuck | post-flight | T2 | final audit, tier1, remediation wave | `plugin/data/references/final-audit-sanity-check.md` |

## Worker router (BB — card phase)

| Symptom | Layer | Tier | Index keywords |
|---------|-------|------|----------------|
| E021 / exit 127 | L5-pre | T1 | E021, worktree_setup |
| Auth / HOME / smoke | L5 | T1→T3 | escalation:coding_agent:auth |
| Delegation / stale skill | L5 | T1/T2 | worker codes directly, devops |
| Eval chain DENY | L6 | T1 | E001–E020, recover.py (E021 = L5-pre) |

## Default chat router

| Intent | Load | Notes |
|--------|------|-------|
| Plan / harden / optimize | `kanban-planning` | Any profile |
| Execute / decompose | `kanban-advanced` → handoff script | Not manual decompose from wrong profile |
| Install / bootstrap / Update Plugin | — | T1–T2 | MBB | `wiki/plugin-verification.md` |
| Something broke | Index + `wiki/troubleshooting.md` | Symptom keyword search |

## T3 — Operator-only (exhaust T1/T2 first)

- OAuth / `agent login`, `HOME=` in gateway env
- `.worktreeinclude` edits, cross-mount repo relocate (E011)
- Plugin Update / init / materialize
- `P004` human approval for >3 files
- Stripe / prod secrets / legal gates

## Cross-references

- Index SSOT: `plugin/skills/kanban-advanced/references/in-flight-governance-index.md`
- Full stack: [[governance]]
- Handoff regression: `plugin/data/references/handoff-regression-checklist.md`
- Operator provisioning: `plugin/data/references/operator-provisioning.md`
