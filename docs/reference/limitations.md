# Limitations

What the plugin CAN'T do — these remain manual or bootstrap-only because the plugin API doesn't cover them:

| Capability | Why not plugin | Handled by |
|-----------|---------------|------------|
| Profile creation | Init shells out to `hermes profile create --no-skills` (not available as a plugin API tool) | `hermes kanban-advanced init` or dashboard **Bootstrap** |
| Gateway dispatch management | Dispatcher is a core gateway feature | User starts gateway separately |
| Cron job creation | Plugin can't call the `cronjob` tool during init | `kanban-advanced init` documents the cron commands |
| Worktree path configuration | Project-specific paths | Config overlay in `.hermes/kanban-overrides/` |
| Coding-agent vendor auth (API keys / OAuth) | Bootstrap does not write `GROK_API_KEY`, `ANTHROPIC_API_KEY`, etc.; advisory smoke only — does not block init | Operator adds keys to `.env` or runs vendor login on gateway host; **preflight** + **pre-dispatch gate** block if smoke still fails — [`coding-agent-auth.md`](../../plugin/data/references/coding-agent-auth.md) |
| Agent binary verification | Plugin can't check `agent --version` | `kanban-advanced init` advisory smoke; blocking `check_coding_agent_cli.py` at preflight |
| Token attribution | Plugin can't inject token logging into the orchestrator's eval loop | Built into `kanban-advanced:kanban-orchestrator` skill |
