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
| How does init / bootstrap work? (profiles, SOUL, skills) | `wiki/bootstrap.md` |
| How do I configure it? | `wiki/configuration.md` |
| Which coding agent / model does the worker use? | `docs/reference/coding-agents.md` |
| Headless CLI flags (smoke + dispatch per binary)? | `plugin/data/references/coding-agent-cli-invocation.md` |
| How does governance work? | `wiki/governance.md` |
| Why block-on-create / decomposition workflow? | `wiki/decomposition-workflow.md` |
| Something is broken | `wiki/troubleshooting.md` |
| Coding agent auth / smoke failed (bootstrap passed, workers block) | `plugin/data/references/coding-agent-auth.md` → then `wiki/troubleshooting.md` |
| Bootstrap limitations (advisory smoke vs blocking gate) | `wiki/bootstrap.md` § Coding-agent auth during bootstrap |
| How do I handle rate limits? | `wiki/provider-strategy.md` |
| What's the DMAIC mapping? | `wiki/six-sigma-mapping.md` |
| Where are upstream docs? | `wiki/external-references.md` |

## Requirements

- Hermes Agent **≥ 0.16.0** (see `wiki/setup.md`)

## When a user has coding-binary auth trouble

Bootstrap smoke is **advisory** — init can succeed with `! coding CLI auth/model check failed`. **Preflight and pre-dispatch gate block decomposition.**

1. Load `plugin/data/references/coding-agent-auth.md` (SSOT).
2. Confirm they authenticated the **coding CLI** (API key in `.env` or vendor login on gateway host) — not only Hermes profile OAuth.
3. Run:
   ```bash
   grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env
   PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
   ```
4. If `HOME: unbound variable` — set `HOME=` in `.env` or gateway systemd; restart gateway.
5. After any auth fix: `rm -f .hermes/kanban/preflight_cache.json` and re-run `preflight.sh` / `pre_dispatch_gate.sh`.

Do **not** tell the user bootstrap alone proves workers can dispatch the coding agent.

## Key commands

- `hermes kanban-advanced init` — bootstrap project (dispatch profiles, config, cron scripts; **advisory** coding-agent smoke only)
- `hermes kanban-advanced decompose --plan <file>` — create cards from a plan
- `hermes kanban-advanced list` — board status
- `hermes kanban-advanced validate` — pre-dispatch validation
- `hermes kanban-advanced preflight <plan-id>` — environment gate

## Plugin skills

All skills are namespaced as `kanban-advanced:kanban-*`. Load them with `skill_view("kanban-advanced:kanban-planning")`, etc.

## Documentation

- User docs: `docs/` (Diátaxis: tutorial, how-to, reference, explanation)
- Agent wiki: `wiki/` (detailed agent-facing reference)
- Full README: `README.md`
- LLM-friendly index: `llms.txt`
