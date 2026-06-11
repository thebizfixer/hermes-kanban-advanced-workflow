# Dashboard API

The Kanban-Advanced settings tab registers as a Hermes dashboard tab at `/kanban-advanced`
(positioned after the Skills tab). The UI is served from `dashboard/index.html` /
`dashboard/dist/index.js`; the backend routes live in `dashboard/plugin_api.py`.

Base path: `/api/plugins/kanban-advanced/`

All endpoints return JSON.

## `GET /api/plugins/kanban-advanced/status`

Returns current initialization state and config values.

**Query parameters (optional):**

| Param | Default | Meaning |
|-------|---------|---------|
| `probe` | `0` | When `1`, ping each dispatch profile model (`hermes chat -q "say ok"`). Skipped by default for fast tab loads. |
| `git_fetch` | `0` | When `1`, run `git fetch origin` before computing `plugin_behind`. Skipped by default; uses a short-lived server cache or local `rev-list` only. |

The dashboard loads **`/status`** first (fast), then **`/status?probe=1&git_fetch=1`** in the background. Returning to the tab in the same browser session reuses **sessionStorage** for the last full payload when probe results are younger than ~3 minutes.

**Response:**
```json
{
  "config_exists": true,
  "project_root": "/path/to/your/project",
  "config_path": "/path/to/.hermes/kanban-overrides/kanban-config.yaml",
  "working_branch": "main",
  "default_working_branch": "main",
  "trigger_branch": "",
  "coding_agent": "agent",
  "coding_agent_binary": "agent",
  "coding_agent_model": "auto",
  "coding_agent_cli": {
    "binary": "agent",
    "display_name": "Cursor CLI",
    "on_path": true,
    "model": "auto",
    "model_label": "Auto (CLI default)",
    "model_configured": true,
    "model_reachable": true,
    "supports_model_pick": true
  },
  "policy_profile": "balanced",
  "max_turns": 180,
  "profiles": {
    "orchestrator": { "exists": true, "has_model": true, "model": "deepseek-v4-pro" },
    "worker": { "exists": true, "has_model": true, "model": "deepseek-v4-pro" }
  },
  "gateway": {
    "running": true,
    "outdated": false
  },
  "status_checks": {
    "probe": false,
    "git_fetch": false
  },
  "hermes_home": "/home/user/.hermes-state/sentimentary",
  "plugin_install_path": "/home/user/.hermes-state/sentimentary/plugins/kanban-advanced",
  "plugin_can_update": true,
  "plugin_up_to_date": true,
  "plugin_behind": 0,
  "plugin_update_available": false
}
```

**Path resolution:** `hermes_home` follows `$HERMES_HOME` (or `$HERMES_STATE_DIR`, then platform defaults — same as `scripts/lib/hermes_home.sh` and Hermes `get_hermes_home()`). `plugin_install_path` is `$HERMES_HOME/plugins/kanban-advanced` when that directory exists; otherwise the running plugin checkout.

**Plugin update fields** (full check uses `git fetch` + `rev-list` when `git_fetch=1`; fast loads use cache or local `rev-list` only):

| Field | Meaning |
|-------|---------|
| `plugin_can_update` | Installed copy is a git checkout (`.git` present) |
| `plugin_up_to_date` | `true` when behind count is 0; `null` when not checkable |
| `plugin_behind` | Commits behind upstream; `null` when not checkable |
| `plugin_update_available` | `true` when `plugin_behind > 0` |
| `plugin_local_changes` | Porcelain dirty count in `plugin_install_path`; `null` when not checkable |

`coding_agent_cli.model_reachable` is populated when `probe=1` (same slow path as Hermes profile model pings). Use `GET /api/plugins/kanban-advanced/coding-agent/models?binary=agent` to populate the dashboard model picker.

When `config_exists` is false, the dashboard shows the bootstrap form.

The status banner shows **Initialized (Up-to-date)** or **Initialized (Update Plugin)** when `plugin_can_update` is true. **Update Plugin** calls `POST /api/plugins/kanban-advanced/update` (git pull in `plugin_install_path`, then re-materialize skills and cron scripts). Disabled when up to date.

Use `project_root` to confirm the API resolved the correct repo (especially after `hermes update` or when multiple clones are on disk). If it points at the plugin install tree, set `KANBAN_PROJECT_ROOT` to your application repo before opening the tab.

## `GET /api/plugins/kanban-advanced/coding-agent/models`

Lists model IDs for the dashboard coding-agent picker.

**Query:** `binary` (required) — e.g. `agent`, `claude`, `codex`.

**Response:**

```json
{
  "binary": "agent",
  "source": "cli",
  "supports_model_pick": true,
  "models": [
    { "id": "auto", "label": "Auto (CLI default)" },
    { "id": "composer-2.5", "label": "Composer 2.5 (current)" }
  ]
}
```

Cursor uses `agent --list-models`. Other supported binaries return curated defaults until a list command is wired in `plugin/coding_agent.py`.

## `POST /api/plugins/kanban-advanced/init`

Runs the equivalent of `hermes kanban-advanced init --force` with the provided parameters.

**Dispatch profiles:** Creates `kanban-advanced-orchestrator` and `kanban-advanced-worker` via `hermes profile create --no-skills`, installs `SOUL.md` from plugin prompts, seeds role-only profile skills (2 / 9), writes `.no-bundled-skills`, and verifies. Logs `HERMES_HOME:` and resolved profile paths in `output`. See `wiki/bootstrap.md`.

**Re-init behavior:** If `kanban-config.yaml` already exists, `working_branch`, `trigger_branch`, and `policy_profile` are **preserved from the file** unless the request body includes overrides. First-time bootstrap uses form values. Bootstrap re-runs profile reconciliation (safe for fixing skill/SOUL drift). To change settings on an initialized project, edit fields and click **Save**. **Save** persists form values and also reconciles profiles. To update the plugin package itself, use **Update Plugin** on the tab.

**Request:**
```json
{
  "working_branch": "main",
  "trigger_branch": "",
  "coding_agent_binary": "agent",
  "coding_agent_model": "auto",
  "policy_profile": "balanced",
  "max_turns": 180
}
```

`coding_agent_model`: `auto` or a CLI-specific model ID (see `GET …/coding-agent/models`).

`policy_profile`: `advisory` | `balanced` | `strict` — governance enforcement level (default `balanced`).

**Response:**
```json
{
  "success": true,
  "output": [
    "   HERMES_HOME: /path/to/.hermes",
    "   OK kanban-advanced-worker",
    "   OK kanban-advanced-orchestrator",
    "   OK kanban-advanced-worker: model configured",
    "   OK kanban-advanced-orchestrator: max_turns = 180",
    "   OK kanban-advanced-worker: SOUL.md <- worker.md (.../profiles/kanban-advanced-worker)",
    "   OK kanban-advanced-worker: 2 skills seeded [...] (.../profiles/kanban-advanced-worker)",
    "   OK Profiles verified: kanban-advanced-worker, kanban-advanced-orchestrator (role skills only)",
    "   OK 'agent' found on PATH",
    "   coding_agent_binary: agent",
    "   coding_agent_model: auto (Auto (CLI default))",
    "   OK coding CLI reachable (Auto (CLI default))",
    "   OK /path/to/kanban-config.yaml",
    "   OK 11 skills -> ...",
    "   OK auto_unblock.sh -> ...",
    "   OK board_keeper.sh -> ...",
    "   OK token_tracker.py -> ...",
    "   OK",
    "   OK Gateway running",
    "OK kanban-advanced is ready!"
  ]
}
```

## `POST /api/plugins/kanban-advanced/save`

Saves settings in an already-initialized config (dashboard button: **Save**). Writes to `kanban-config.yaml` and `.env`. Request body values for `working_branch`, `trigger_branch`, `coding_agent_binary`, and `coding_agent_model` are applied as submitted. Runs a coding-CLI smoke test when the binary is on PATH. This endpoint does not pull or upgrade the plugin — use Hermes plugin **Pull** for that.

**Request:** Same shape as init.

**Response:** Same shape as init (re-runs materialization but skips profile creation). Optional overlay keys not in the managed set (e.g. `feature_branch_prefix`) are preserved.

## `POST /api/plugins/kanban-advanced/update`

Git-pull the plugin install checkout, refresh materialized skills/scripts under `$HERMES_HOME`, and **reconcile dispatch profiles** (SOUL, role-only skills, verification).

**Request:** Empty body.

**Response:**
```json
{
  "success": true,
  "unchanged": false,
  "output": [
    "=== Updating plugin at /path/to/.hermes/plugins/kanban-advanced ===",
    "Already up to date.",
    "   OK 11 skills -> ...",
    "OK Plugin updated"
  ]
}
```

When already up to date, `unchanged` is `true` and pull is skipped.

**Local changes in the install dir:** `plugin_install_path` is a read-only mirror of upstream on every platform (Linux, macOS, Windows native, WSL). If `git status` shows local modifications (line-ending drift, editor saves, or edits in the install tree), the update endpoint discards them with `git reset --hard` and `git clean -fd` before pull, then falls back to `git reset --hard <upstream>` if `pull --ff-only` still fails. Edit your **project** repo or fork — not the Hermes plugin install directory.

**Errors:**
- `"Plugin install is not a git checkout"` — no `.git` in install path
- `"git not found on PATH"`
- `"Could not determine upstream"` — no tracking branch / fetch failed
- git pull stderr on merge conflicts or non-ff updates

## Error response

```json
{
  "error": "Descriptive error message"
}
```

Common errors:
- `"API unreachable"` — gateway not running
- `"Config file not found"` — attempting save before init
- `"hermes CLI not found on PATH"` — can't run init
