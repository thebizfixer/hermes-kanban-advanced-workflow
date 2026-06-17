# Configuration reference

Overlay file: `.hermes/kanban-overrides/kanban-config.yaml` — created automatically by:

- **CLI:** `hermes kanban-advanced init` (interactive — step 1c lists commands **on PATH**; sets `coding_agent_binary` and `coding_agent_model`, with CLI smoke test)
- **Dashboard:** Hermes dashboard → **Kanban-Advanced** tab → **Bootstrap** (same as init) or **Save** (persists binary + model + other fields; plugin upgrades use **Update Plugin** on the tab)

To create manually:

```bash
cp hermes-kanban-advanced-workflow/kanban-config.example.yaml .hermes/kanban-overrides/kanban-config.yaml
```

Schema: [`schema/kanban-config.schema.json`](../../schema/kanban-config.schema.json) · Example: [`kanban-config.example.yaml`](../../kanban-config.example.yaml) · Dashboard API: [`dashboard/API.md`](../../dashboard/API.md)

## Re-init

`hermes kanban-advanced init` and dashboard **Bootstrap** refresh dispatch profiles (SOUL.md, role-only skills, verification), shared materialized skills, and cron scripts. When `kanban-config.yaml` already exists, branch settings are kept unless you pass explicit overrides. Use dashboard **Save** (not Bootstrap) to persist parameter edits after changing form fields. **Working branch** defaults from git upstream / `origin/HEAD` / local `HEAD`. **Trigger branch** is optional — when unset, E009 deploy-branch rules are disabled.

Full bootstrap behavior: [wiki/bootstrap.md](../../wiki/bootstrap.md).

**Operator provisioning:** Init writes kanban keys to `.env` and kanban paths to `.worktreeinclude` only. Application secrets, `.env` in worktrees, and runtime deps (`.venv/`, `node_modules/`) are operator responsibility — [operator-provisioning.md](../../plugin/data/references/operator-provisioning.md).

## Project root (dashboard)

The settings API resolves the repo that owns the overlay. Override when the gateway cwd is ambiguous:

| Variable | Purpose |
| --- | --- |
| `KANBAN_PROJECT_ROOT` | Absolute path to your application repo |
| `HERMES_PROJECT_ROOT` | Same (alias) |
| `HERMES_KANBAN_CONFIG` | Absolute path to `kanban-config.yaml` |

See [wiki/troubleshooting.md](../../wiki/troubleshooting.md) if `working_branch` shows `main` after a Hermes update.

## Required

| Key | Substituted as | Purpose |
| --- | --- | --- |
| `schema_version` | — | Overlay contract (`1.0.0`) |
| `working_branch` | `${working_branch}` | Integration branch (e.g. `main`) |
| `orchestrator_profile` | `${orchestrator_profile}` | Root / gate / audit cards |
| `worker_profile` | `${worker_profile}` | Implementation cards |
| `skills_output_path` | — | Skill output directory (for advanced configuration) |
| `bundle_path` | `${bundle_path}` | Path to this plugin in the repo |

## Common optional keys

| Key | Substituted as | Default |
| --- | --- | --- |
| `trigger_branch` | `${trigger_branch}` | unset — protected deploy branch; E009 when set |
| `bundle_version` | — | Pin public release tag (documentation) |
| `coding_agent_binary` | `${coding_agent_binary}` | Exact CLI command on PATH (e.g. `cursor-agent`, `claude`) — set during init from on-PATH list; see [coding agents](coding-agents.md) |
| `coding_agent_model` | — (runtime: `KANBAN_CODING_AGENT_MODEL` in `.env`) | `auto` — CLI default; or a tool-specific ID (Cursor: `cursor-agent --list-models` or `agent --list-models`). Worker dispatch: `scripts/coding_agent_invoke.sh` — see `plugin/data/references/coding-agent-cli-invocation.md` |
| `preflight_profiles` | — | `kanban-advanced-worker,kanban-advanced-orchestrator` |
| `plan_memory_path` | `${plan_memory_path}` | `.hermes/kanban/memory` |
| `feature_branch_prefix` | — | `kanban/` |
| `required_secrets` | — | project-specific |
| `preflight_api_url` | — | empty skips API check |
| `gateway_timeout_seconds` | — | `1800` |
| `escalation_max_attempts` | — | Per-level retry thresholds (`coding_agent`, `worker`, `orchestrator`; default `3` each). Required by `kanban_escalation_tracker.sh`. |
| `hermes_home_hint` | — | Operator docs only (not written to skills) |

## Policy profiles

`policy_profile` in `kanban-config.yaml` and `KANBAN_POLICY_PROFILE` in `.env`: `advisory` | `balanced` | `strict`. Set at init (CLI or dashboard). Governs card policy, evaluation chain, and validation scripts. See [wiki/configuration.md](../../wiki/configuration.md) § Policy profiles.

## Profiles

Default dispatch profile names: `kanban-advanced-orchestrator`, `kanban-advanced-worker`. Init creates them with `--no-skills`, installs plugin SOUL prompts, and seeds role-only profile skills. Each assignee profile needs `config.yaml` with `model.default` and `model.provider`. Preflight validates profiles listed in `preflight_profiles`.

See [wiki/bootstrap.md](../../wiki/bootstrap.md) for init/profile detail and [wiki/configuration.md](../../wiki/configuration.md) for thinking levels and Hermes v0.15.x kanban config keys.
