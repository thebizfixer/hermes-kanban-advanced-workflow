# How to: provider strategy

True parallel dispatch across profiles needs **separate provider capacity per role** when rate limits apply. Otherwise tasks serialize on one provider.

| Role | Typical thinking | Notes |
| --- | --- | --- |
| Orchestrator | high | Planning, audit, reconcile |
| Worker | medium | Supervision, verification |
| Headless coding agent | low / off | Invoked via `agent -p` in card body |

See [wiki/provider-strategy.md](../../wiki/provider-strategy.md) for capacity planning detail.
