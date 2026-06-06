# Interaction model

The kanban-advanced workflow uses **explicit user triggers** — the orchestrator does not auto-advance through planning checkpoints.

## Planning stages

| Stage | User trigger (examples) | Skill |
| --- | --- | --- |
| Draft | "draft a plan", "start planning" | `kanban-advanced:kanban-planning` |
| Harden | "harden the plan" | `kanban-advanced:kanban-planning` |
| Revise | "revise …" | `kanban-advanced:kanban-planning` |
| Optimize | "optimize for dispatch" | `kanban-advanced:kanban-planning` |

## Execution

| Trigger | Action |
| --- | --- |
| "proceed", "execute", "walk away" | Preflight → decomposition → dispatch |
| "stop", "pause board" | Block or pause via `hermes kanban` |

## Interrupts

- **Reset plan memory:** delete `.hermes/kanban/memory/<plan_id>.json` only when replanning from scratch.
- **Re-install:** after editing skills, re-install the plugin to pick up changes.

See `docs/tutorial/kanban-advanced-tutorial.md` for first-time setup.
