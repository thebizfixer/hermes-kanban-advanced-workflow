---
name: kanban-advanced
description: Entry point for the kanban-advanced multi-agent governance workflow. Load this skill when the user asks to plan, harden, optimize, decompose, or execute work through a governed pipeline.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, governance, planning, execution]
---

# Kanban-Advanced Workflow

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `sentimentary-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Load the right skill and get to work — no profile switch needed for planning and hardening.

## When to load this skill

Load this skill when the user says any of these trigger phrases:
- "Plan this out"
- "Harden the plan"
- "Optimize for Kanban"
- "Execute the plan"
- "Do a sanity check"
- "kanban workflow"
- "governed plan"
- "kanban-advanced"
- Any mention of decomposing work into cards or dispatching workers

## What to do

Load the skill that matches the user's request and proceed. All kanban-advanced skills work from any profile — the orchestrator/worker split is only needed for dispatch, not for planning.

### Picking the right skill

| User says | Load | Why |
|-----------|------|-----|
| "Plan this out" | `kanban-advanced:kanban-planning` | Draft stage — write a new plan |
| "Do a sanity check" / review a plan | `kanban-advanced:kanban-planning` | Sanity check stage — read-only audit, find gaps |
| "Harden the plan" | `kanban-advanced:kanban-planning` | Harden stage — close the gaps |
| "Optimize for Kanban" | `kanban-advanced:kanban-planning` | Optimize stage — prep for decomposition |
| "Execute the plan" / "decompose" / "proceed" | `kanban-advanced:kanban-orchestrator` | Decomposition + dispatch — needs orchestrator profile for kanban create |
| Preflight before dispatch | `kanban-advanced:kanban-preflight` | Environment gating |
| Worker hit a DENY / block | `kanban-advanced:kanban-worker-governance` | Error code reference |
| Orchestrator hit a governance block | `kanban-advanced:kanban-orchestrator-governance` | Pitfall encyclopedia |

### When you DO need the orchestrator profile

Only these operations require the orchestrator profile (because the dispatcher matches `assignee` to profile name):
- `hermes kanban create` — card creation
- `hermes kanban complete` — card completion
- `hermes kanban block/unblock/link` — board management

When the user says "execute the plan" and you're not on orchestrator, prefer the
**board-mediated handoff** — no human session switch required:

1. Create one hardened handoff card assigned to the orchestrator profile:

```bash
python3 scripts/kanban_handoff.py --plan <plan.md>
```

   The gateway dispatcher claims the `ready` card and spawns an orchestrator-profile
   agent that runs the decomposition SOP autonomously. The builder is idempotent
   (one open handoff card per plan_id) and checks its own preconditions.
2. If the builder exits non-zero, relay its `fix` message and act on it:
   - exit 2 — orchestrator profile missing → `hermes kanban-advanced init`
   - exit 3 — gateway not running → ask the user, then `hermes gateway run`
   - exit 4 — dispatcher disabled / `auto_decompose` true → run the printed
     `hermes config set …` fix, then retry
3. **Fallback only** (no gateway / dispatcher unavailable): the user must start a new
   orchestrator session manually — Hermes has **no in-chat profile switch**
   ([upstream slash commands](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)).
   Give them **one** of these (same on Linux, macOS, Windows, WSL), then ask them to
   repeat the trigger: `hermes -p orchestrator chat`, `orchestrator chat` (if that
   alias exists), or `hermes profile use orchestrator` then `hermes chat`. Full
   reference: `plugin/data/references/profile-switching.md`.

## Quick reference

| Skill | Purpose |
|-------|---------|
| `kanban-advanced:kanban-planning` | Write, harden, optimize plans |
| `kanban-advanced:kanban-orchestrator` | Decompose plans, dispatch cards, govern execution |
| `kanban-advanced:kanban-worker` | Worker lifecycle — supervise coding agents |
| `kanban-advanced:kanban-preflight` | Environment gating before dispatch |
| `kanban-advanced:kanban-cleanup` | Post-plan cleanup + postmortem |
| `kanban-advanced:kanban-postmortem` | Postmortem report structure |
| `kanban-advanced:kanban-reconciliation` | Post-execution reconciliation checklist |
| `kanban-advanced:kanban-notify` | Gateway push notifications for walk-away |
| `kanban-advanced:kanban-orchestrator-governance` | Orchestrator pitfall encyclopedia |
| `kanban-advanced:kanban-worker-governance` | Worker error code reference |
