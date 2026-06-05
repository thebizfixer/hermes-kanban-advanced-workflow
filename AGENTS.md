# AGENTS.md

You are helping a user with the kanban-advanced Hermes Agent plugin. This file tells you how to install it and where to find information.

## When a user asks you to install or set up kanban-advanced

Guide them through the tutorial at `docs/tutorial/kanban-advanced-tutorial.md`. The tutorial walks through the complete lifecycle: install → plan → harden → optimize → decompose → execute → reconcile → cleanup.

For a focused install-only path, use `docs/how-to/install-as-plugin.md`.

## When a user asks how to use kanban-advanced

Load the relevant wiki page for detailed instructions:

| Question | Load |
|----------|------|
| How do I set this up? | `wiki/setup.md` |
| How do I configure it? | `wiki/configuration.md` |
| How does governance work? | `wiki/governance.md` |
| Something is broken | `wiki/troubleshooting.md` |
| How do I handle rate limits? | `wiki/provider-strategy.md` |
| What's the DMAIC mapping? | `wiki/six-sigma-mapping.md` |
| Where are upstream docs? | `wiki/external-references.md` |

## Key commands

- `hermes kanban-advanced decompose --plan <file>` — create cards from a plan
- `hermes kanban-advanced list` — board status
- `hermes kanban-advanced validate` — pre-dispatch validation
- `hermes kanban-advanced preflight <plan-id>` — environment gate

## Plugin skills

All skills are namespaced as `plugin:kanban-*`. Load them with `skill_view("plugin:kanban-planning")`, etc.

## Documentation

- User docs: `docs/` (Diátaxis: tutorial, how-to, reference, explanation)
- Agent wiki: `wiki/` (detailed agent-facing reference)
- Full README: `README.md`
- LLM-friendly index: `llms.txt`
