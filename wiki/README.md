# Wiki — Agent-facing reference

> **For the agent:** When a user asks a question about kanban-advanced, load the relevant page from this wiki. These pages are written for you (the agent) to read and use.

| Page | What it covers |
|------|---------------|
| [setup.md](setup.md) | Agent setup guide — install plugin, bootstrap project |
| [bootstrap.md](bootstrap.md) | **Init / Bootstrap** — dispatch profiles, SOUL.md, skill isolation, `HERMES_HOME`, verification |
| [configuration.md](configuration.md) | Config reference — overlay variables, profiles, thinking levels, policy profiles |
| [governance.md](governance.md) | **Full pre-execution stack** (plan → worker), four gates, pre-dispatch gate, evaluation chain, recovery |
| [in-flight-navigation.md](in-flight-navigation.md) | **Sad-path router** — belt × layer, orchestrator/worker/chat tables, T3 boundaries |
| [decomposition-workflow.md](decomposition-workflow.md) | **Why** block-on-create, gate card, `auto_decompose=false` — agent FAQ for decomposition |
| [troubleshooting.md](troubleshooting.md) | Error codes → recovery actions, common failures, quick diagnosis |
| [provider-strategy.md](provider-strategy.md) | Multi-provider fan-out, rate-limit prevention, fallback configuration |
| [six-sigma-mapping.md](six-sigma-mapping.md) | DMAIC pipeline mapping, CTQ tree, defect reduction metrics |
| [external-references.md](external-references.md) | Upstream docs — Hermes Agent, AGT, AEP, coding agents, platform references |

Plugin install: [docs/how-to/install-as-plugin.md](../docs/how-to/install-as-plugin.md)
Full README: [README.md](../README.md)
