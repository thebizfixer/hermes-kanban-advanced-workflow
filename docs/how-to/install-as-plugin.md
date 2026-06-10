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

## Create profiles

The workflow uses two profiles. Choose your own names — the examples below use `orchestrator` and `worker`:

```bash
hermes profile create orchestrator --clone
hermes profile create worker --clone
```

Configure each profile with a model and provider. At minimum, the worker profile needs access to a coding agent CLI.

```bash
hermes config set model.default <your-model> --profile worker
hermes config set model.provider <your-provider> --profile worker
```

---

## Bootstrap your project

```bash
cd your-project
hermes kanban-advanced init --project-root . --working-branch <branch-name>
```

Replace `<branch-name>` with your integration branch (e.g. `main`).

What init provisions:

1. **Config overlay** — `.hermes/kanban-overrides/kanban-config.yaml`
2. **Cron scripts** — `auto_unblock.sh` and `board_keeper.sh` to `$HERMES_HOME/scripts/`
3. **Skill bundle** — `kanban-advanced.yaml` to `$HERMES_HOME/skill-bundles/` (fallback for non-plugin sessions)
4. **Environment** — `HERMES_ENABLE_PROJECT_PLUGINS=true` in `.env`

---

## Verify

```bash
# CLI commands available
hermes kanban-advanced --help

# Skills load (in a Hermes session)
# Use: skill_view("kanban-advanced:kanban-planning")
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
| Init fails with "profile not found" | Create profiles first: `hermes profile create orchestrator --clone` |
| "Project-local plugins are disabled" | Init sets `HERMES_ENABLE_PROJECT_PLUGINS=true` in `.env`. Source it or restart. |
| Cron scripts don't run | Verify they exist at `$HERMES_HOME/scripts/`. Re-run `hermes kanban-advanced init`. |

For more help, see [troubleshooting.md](troubleshooting.md).
