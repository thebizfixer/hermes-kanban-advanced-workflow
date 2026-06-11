# How to: provider strategy

True parallel dispatch across profiles needs **separate provider capacity per role** when rate limits apply. Otherwise tasks serialize on one provider.

| Role | Typical thinking | Notes |
| --- | --- | --- |
| Orchestrator | high | Planning, audit, reconcile |
| Worker | medium | Supervision, verification |
| Headless coding agent | low / off | Configured via `coding_agent_binary` / `KANBAN_CODING_AGENT`; card body carries the prompt only — dispatch via `coding_agent_invoke.sh` |

See [wiki/provider-strategy.md](../../wiki/provider-strategy.md) for capacity planning detail.
