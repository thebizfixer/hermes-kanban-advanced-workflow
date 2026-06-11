# Personas

The workflow uses two agent profiles with a strict separation of concerns.

| Persona          | Role                                                                                | Key Skills                                                                                                                      |
| ---------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator** | PM / Sysadmin — plans, optimizes, attests, decomposes, monitors, audits, reconciles | kanban-advanced:kanban-planning, kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-preflight, kanban-advanced:kanban-notify, kanban-advanced:kanban-reconciliation, kanban-advanced:kanban-postmortem, kanban-advanced:kanban-cleanup |
| **Worker**       | Supervisor — delegates to coding agents, runs evaluation chain, verifies output     | kanban-advanced:kanban-worker                                                                                                                   |

## Worker Lifecycle

```
orient → memory (fast path) → fast-sanity → handoff → monitor → verify (eval chain) → complete
```

The worker is a supervisor, not an implementer. It reads the card, checks the preflight cache (< 30s if fresh), extracts the fenced `agent` prompt block, smokes and dispatches the configured coding CLI via `scripts/coding_agent_invoke.sh`, monitors progress, runs the evaluation chain, and closes the task. See [coding agents](coding-agents.md).
