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
| Why `dispatch_stale_timeout_seconds` is 14400 and where it is set? | `plugin/data/references/dispatch-stale-timeout.md` + `wiki/bootstrap.md` step 13 |
| Which coding agent / model does the worker use? | `docs/reference/coding-agents.md` |
| Headless CLI flags (smoke + dispatch per binary)? | `plugin/data/references/coding-agent-cli-invocation.md` |
| How does governance work? | `wiki/governance.md` (§ Full pre-execution governance stack) |
| Why block-on-create / decomposition workflow? | `wiki/decomposition-workflow.md` |
| Something is broken | `wiki/troubleshooting.md` |
| Supervisor hit a rail mid-card / mid-decompose | `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` or `wiki/in-flight-navigation.md` |
| Coding agent auth / smoke failed (bootstrap passed, workers block) | `plugin/data/references/coding-agent-auth.md` → then `wiki/troubleshooting.md` |
| Bootstrap limitations (advisory smoke vs blocking gate) | `wiki/bootstrap.md` § Coding-agent auth during bootstrap |
| What must the operator provision (.env, worktree, deps)? | `plugin/data/references/operator-provisioning.md` |
| How do I handle rate limits? | `wiki/provider-strategy.md` |
| What's the DMAIC mapping? | `wiki/six-sigma-mapping.md` |
| How do I write / format a plan file? | `skill_view("kanban-advanced:kanban-planning")` + `plugin/data/references/plan-file-format.md` |
| Final audit exit-2 / stuck remediation loop | `plugin/data/references/final-audit-sanity-check.md` |
| Tier 2 false positive / doc-coverage gap | `plugin/data/references/final-audit-doc-coverage.md` |
| E001 ALLOW but Tier 1 `plan_file_zero_diff` | `plugin/data/references/final-audit-sanity-check.md` § Tier 1 ↔ E001 |
| Postmortem `uncaught_violation_count: null` | `kanban-advanced:kanban-postmortem` § Final audit KPIs — re-run audit |
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

## When a user needs help provisioning beyond bootstrap

Init covers **kanban infrastructure only** (profiles, overlay, materialized scripts, kanban `.worktreeinclude` paths). It does **not** add application `.env`, API keys, venvs, or `node_modules`.

1. Load `plugin/data/references/operator-provisioning.md` (SSOT).
2. Ask what they will run through kanban: coding agent binary, auth model, tests (`pytest`/`npm`), DB/API deps, `required_secrets` in overlay.
3. Recommend **main `.env`** entries and **`.worktreeinclude`** lines they must add themselves.
4. Re-run init/Update Plugin if kanban paths are missing; commit `.worktreeinclude`.

Do **not** assume bootstrap copied `.env` into worktrees — the plugin never adds `.env` to `.worktreeinclude` by default.

## Key commands

- `hermes kanban-advanced init` — bootstrap project (dispatch profiles, config, cron script files — not cron jobs; **advisory** coding-agent smoke only)
- `python3 hermes-kanban-advanced-workflow/scripts/kanban_handoff.py --plan <file>` — board-mediated orchestrator handoff (non-orchestrator profiles)
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
