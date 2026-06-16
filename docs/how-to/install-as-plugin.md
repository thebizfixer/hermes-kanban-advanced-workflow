# How to install kanban-advanced

**How-to guide** — Install the kanban-advanced plugin and bootstrap your project. For a complete walkthrough of the entire lifecycle, see the [tutorial](../tutorial/kanban-advanced-tutorial.md).

**Prerequisites:** Hermes Agent ≥ 0.16.0, Python 3.12+, a coding agent CLI on PATH.

---

## Install the plugin

```bash
hermes plugins install thebizfixer/hermes-kanban-advanced-workflow
```

Restart Hermes after install. The plugin's `register(ctx)` runs at startup.

Verify:

```bash
hermes plugins list
# Should show: kanban-advanced  v1.0.0
```

**Desktop users:** If the Hermes Desktop app doesn't have a plugins screen, install via CLI once — all plugin features (skills, tools, CLI) work in desktop sessions after install.

---

## Bootstrap your project

Bootstrap creates dispatch profiles, config, and scripts in one step. You do **not** need to create profiles manually.

```bash
cd your-project
hermes kanban-advanced init --project-root . --working-branch <branch-name>
```

Replace `<branch-name>` with your integration branch (e.g. `main`).

**Dashboard alternative:** Hermes dashboard → **Kanban-Advanced** tab → set **Coding Agent** (binary + model) → **Bootstrap** (same operation as CLI init).

CLI init step **1c** asks for the binary; step **1c-ii** asks for the model (`auto` or an ID — Cursor: live list from `agent --list-models`). Both are smoke-tested when the binary is on PATH.

### Coding-agent auth (before you execute)

Bootstrap smoke is **advisory** — init can succeed even when headless auth is not ready yet (`! coding CLI auth/model check failed` in the log).

| Bootstrap provides | You must provide separately |
| --- | --- |
| `KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, `HOME=` in `.env` | Vendor API keys in `.env` **or** login on the gateway host (`agent login`, `claude login`, `codex login`, …) |

**Blocking checks** run at preflight and pre-dispatch — not during bootstrap. Before your first execute:

```bash
# After adding keys or running vendor login
grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
```

SSOT: [`plugin/data/references/coding-agent-auth.md`](../../plugin/data/references/coding-agent-auth.md). Agent playbook: [`AGENTS.md`](../../AGENTS.md) § *When a user has coding-binary auth trouble*.

### Operator provisioning (what you add yourself)

Bootstrap does **not** set up your application for card worktrees. Based on what you plan to run through kanban:

| Your plan | You typically add |
| --- | --- |
| OAuth coding agent (Cursor), no cwd `.env` tests | Gateway login + `HOME` (init writes) — often no extra `.worktreeinclude` lines |
| API-key coding agent (Codex, Grok, …) | Keys in `.env`; add **`.env`** to `.worktreeinclude` |
| `pytest` / DB / API integration tests in worktrees | App secrets in `.env`; **`.env`** + often **`.venv/`** in `.worktreeinclude` |
| Frontend tests | **`.env`** + **`node_modules/`** (or your install policy) |

Init merges kanban paths into `.worktreeinclude` and **preserves** lines you add (e.g. `.env`). Commit the file after bootstrap.

Full decision guide: [`operator-provisioning.md`](../../plugin/data/references/operator-provisioning.md). Agent help: [`AGENTS.md`](../../AGENTS.md) § *When a user needs help provisioning beyond bootstrap*.

### Dispatch profiles (created by init)

| Role | Profile name |
| --- | --- |
| Orchestrator | `kanban-advanced-orchestrator` |
| Worker | `kanban-advanced-worker` |

Init:

- Creates profiles with `hermes profile create <name> --no-skills` (no Hermes bundled skills)
- Copies model/auth `config.yaml` / `.env` from default
- Installs `SOUL.md` from `plugin/data/prompts/orchestrator.md` and `worker.md`
- Seeds **role-only** skills into each profile's `skills/` directory (2 worker / 9 orchestrator)
- Writes `.no-bundled-skills` to prevent `hermes update` from re-injecting default skills
- Verifies the end state (fails if verification does not pass)

Legacy profiles named `orchestrator` / `worker` are renamed automatically.

Agent reference: [wiki/bootstrap.md](../../wiki/bootstrap.md)

### What init also provisions

1. **Config overlay** — `.hermes/kanban-overrides/kanban-config.yaml`
2. **Shared skill materialization** — all 12 skills → `$HERMES_HOME/skills/kanban-advanced/`
3. **Cron scripts (files only)** — `auto_unblock.sh`, `board_keeper.sh`, `token_tracker.py` → `$HERMES_HOME/scripts/`. Hermes cron **jobs** are created per plan at decomposition (`provision_kanban_crons.sh --create`), not at init.
4. **Environment** — `HERMES_ENABLE_PROJECT_PLUGINS=true`, `KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, `KANBAN_POLICY_PROFILE`, `HOME` in `.env` (kanban keys only — not app secrets)
5. **`.worktreeinclude`** — kanban gitignored paths for card worktrees (overlay, invoke scripts); **you** add `.env` / `.venv/` as needed

Configure **Hermes dispatch profile** models (orchestrator / worker) separately from the **coding CLI** model — see [wiki/configuration.md](../../wiki/configuration.md) and [coding agents](../reference/coding-agents.md).

---

## Verify

```bash
# CLI commands available
hermes kanban-advanced --help

# Dispatch profile skill counts
hermes profile show kanban-advanced-worker | grep Skills:      # expect 2
hermes profile show kanban-advanced-orchestrator | grep Skills:  # expect 9

# SOUL prompts
head -1 "$(hermes profile show kanban-advanced-worker | awk '/^Path:/ {print $2}')/SOUL.md"
# # Worker Prompt
```

---

## Next: start the gateway and run your first plan

```bash
hermes gateway run
```

Follow the [tutorial](../tutorial/kanban-advanced-tutorial.md) for a guided walkthrough of writing and executing your first plan.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Plugin doesn't appear in `hermes plugins list` | Restart Hermes. The plugin loader runs at startup. |
| `hermes kanban-advanced: command not found` | The CLI group is `kanban-advanced`, not `kanban`. |
| Init fails with "profile not found" | Re-run init; accept profile create prompts or use `--force` |
| Profiles have 90+ skills after bootstrap | Wrong `HERMES_HOME` or stale plugin — see [wiki/bootstrap.md](../../wiki/bootstrap.md) |
| "Profile reconciliation/verification failed" | Read bootstrap output issues; Update Plugin + restart gateway |
| Bootstrap OK but execute fails on coding agent | Bootstrap does not block on auth — run `check_coding_agent_cli.py`, fix keys/OAuth/`HOME` — [coding-agent auth](../../plugin/data/references/coding-agent-auth.md) |
| "Project-local plugins are disabled" | Init sets `HERMES_ENABLE_PROJECT_PLUGINS=true` in `.env`. Source it or restart. |
| Cron scripts don't run | Script files: `$HERMES_HOME/scripts/`. Jobs: `hermes cron list` + gateway running. Create per plan: `provision_kanban_crons.sh --create`. |

For more help, see [troubleshooting.md](troubleshooting.md) and [wiki/bootstrap.md](../../wiki/bootstrap.md).
