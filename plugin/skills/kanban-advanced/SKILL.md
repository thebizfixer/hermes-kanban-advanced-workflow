---
name: kanban-advanced
description: Entry point for the kanban-advanced multi-agent governance workflow. Load this skill when the user asks to plan, harden, optimize, decompose, or execute work through a governed pipeline.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, governance, planning, execution]
---

# Kanban-Advanced Workflow

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

When the user says "execute the plan" and you're not on orchestrator, tell them:
"I need the orchestrator profile to dispatch cards. Run `hermes -p orchestrator` and I'll pick up from there — the orchestrator hook will auto-load the full SOP."

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
