# Recommended SOUL.md Startup Rule (Postmortem R3)

Add to the coding agent's Hermes profile SOUL.md to cap orientation waste.

## Rule

> You have 30 seconds to orient. Read the card body. Extract the `agent -p` block.
> Do not read the codebase — that is the coding agent's job.
> Send a heartbeat within 2 minutes of claiming the task.
> If you cannot find the `agent -p` block, block the card immediately with reason "P002: agent prompt missing".

## Why

The 2026-05-07 postmortem (18 tasks on a prior host run) found average orientation waste of
16 minutes per task — workers reading arbitrary codebase files before taking their first
productive action. Fast tasks had zero orientation phase. This rule constrains the default
exploration-heavy behavior.

## Where to add it

In your Hermes profile's `SOUL.md` (e.g. `.hermes/profiles/<worker-profile>/SOUL.md`),
append:

    ## Kanban startup rule
    When working a kanban task, you have 30 seconds to orient.
    Read the card body. Find the agent -p block. Spawn it. Do not explore the codebase.
    Send a heartbeat (kanban_heartbeat) within 2 minutes of claiming the task.
    If no agent -p block exists, block the card immediately: P002 — agent prompt missing.

## Relationship to plugin governance

This rule is enforced at the Hermes profile level (not by plugin scripts). The plugin's
`worktree_setup.sh` enforces the git-level constraints (no unauthorized push, Files: boundary).
The SOUL.md rule enforces the time budget. Both are needed.
