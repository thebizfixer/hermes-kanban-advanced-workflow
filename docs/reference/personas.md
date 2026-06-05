# Personas

The workflow uses two agent profiles with a strict separation of concerns.

| Persona          | Role                                                                                | Key Skills                                                                                                                      |
| ---------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator** | PM / Sysadmin — plans, optimizes, attests, decomposes, monitors, audits, reconciles | kanban-planning, kanban-orchestrator, kanban-preflight, kanban-notify, kanban-reconciliation, kanban-postmortem, kanban-cleanup |
| **Worker**       | Supervisor — delegates to coding agents, runs evaluation chain, verifies output     | kanban-worker                                                                                                                   |

## Worker Lifecycle

```
orient → memory (fast path) → fast-sanity → handoff → monitor → verify (eval chain) → complete
```

The worker is a supervisor, not an implementer. It reads the card, checks the preflight cache (< 30s if fresh), extracts the `agent -p` block, spawns the coding agent, monitors progress, runs the evaluation chain, and closes the task.
