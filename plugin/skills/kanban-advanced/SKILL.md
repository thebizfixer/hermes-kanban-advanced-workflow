---
name: kanban-advanced
description: Entry point for the kanban-advanced multi-agent governance workflow. Load this skill when the user asks to plan, harden, optimize, decompose, or execute work through a governed pipeline.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, governance, planning, execution]
---

# Kanban-Advanced Workflow

You are about to enter a governed multi-agent workflow. This skill bridges you from the default profile to the orchestrator.

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

1. **Switch to the orchestrator profile.** Tell the user: "I need to switch to the orchestrator profile for this. Run `hermes -p orchestrator` and I'll guide you from there."
2. Once on the orchestrator profile, the `on_session_start` hook will auto-load the full `plugin:kanban-orchestrator` skill with the complete SOP.
3. If the user is already on the orchestrator profile, load `plugin:kanban-orchestrator` directly.

## Quick reference

| User says | Load |
|-----------|------|
| "Plan this out" | `plugin:kanban-planning` |
| "Harden the plan" | `plugin:kanban-planning` |
| "Optimize for Kanban" | `plugin:kanban-planning` |
| "Execute the plan" | `plugin:kanban-orchestrator` |
| Decomposition questions | `plugin:kanban-orchestrator` |
| Worker/verification questions | `plugin:kanban-worker` |
| Preflight questions | `plugin:kanban-preflight` |
| Governance questions | `plugin:kanban-orchestrator-governance` |
