# Personas

The workflow uses two agent profiles with a strict separation of concerns.

| Persona | Belt | Role | Key skills | Sad-path first load |
| ------- | ---- | ---- | ---------- | ------------------- |
| **Orchestrator** | MBB | Plans, attests, decomposes, monitors, reconciles | `kanban-planning`, `kanban-orchestrator`, `kanban-preflight`, … | `kanban-orchestrator-governance` + in-flight index L0–L4 |
| **Worker** | BB | Supervises coding agent; eval chain | `kanban-git`, `kanban-worker`, `kanban-worker-governance` | `kanban-worker-governance` + in-flight index L5–L6 |
| **Coding agent** | GB | Implements within `Files:` / `Mode:` | (external CLI) | Escalation via worker only |
| **Crons** | Yellow | `auto_unblock`, `board_keeper` | (scripts) | `wiki/governance.md` § Auto-progression |

Index: `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")`. Hub: [`wiki/in-flight-navigation.md`](../../wiki/in-flight-navigation.md).

## Worker Lifecycle

```
orient → memory (fast path) → fast-sanity → handoff → monitor → verify (eval chain) → complete
```

The worker is a supervisor, not an implementer. It reads the card, checks the preflight cache (< 30s if fresh), extracts the fenced `agent` prompt block, smokes and dispatches the configured coding CLI via `scripts/coding_agent_invoke.sh`, monitors progress, runs the evaluation chain, and closes the task. See [coding agents](coding-agents.md).
