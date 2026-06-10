# Dashboard API

The Kanban-Advanced settings tab registers as a Hermes dashboard tab at `/kanban-advanced`
(positioned after the Skills tab). The UI is served from `dashboard/index.html` /
`dashboard/dist/index.js`; the backend routes live in `dashboard/plugin_api.py`.

Base path: `/api/plugins/kanban-advanced/`

All endpoints return JSON.

## `GET /api/plugins/kanban-advanced/status`

Returns current initialization state and config values.

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
  "policy_profile": "balanced",
  "max_turns": 180,
  "profiles": {
    "orchestrator": { "exists": true, "has_model": true, "model": "deepseek-v4-pro" },
    "worker": { "exists": true, "has_model": true, "model": "deepseek-v4-pro" }
  },
  "gateway": {
    "running": true,
    "outdated": false
  }
}
```

When `config_exists` is false, the dashboard shows the bootstrap form.

Use `project_root` to confirm the API resolved the correct repo (especially after `hermes update` or when multiple clones are on disk). If it points at the plugin install tree, set `KANBAN_PROJECT_ROOT` to your application repo before opening the tab.

## `POST /api/plugins/kanban-advanced/init`

Runs the equivalent of `hermes kanban-advanced init --force` with the provided parameters.

**Re-init behavior:** If `kanban-config.yaml` already exists, `working_branch`, `trigger_branch`, and `policy_profile` are **preserved from the file** unless the request body includes overrides. First-time bootstrap uses form values. To change settings on an initialized project, prefer **Update settings**; Bootstrap re-runs profile creation and materialization.

**Request:**
```json
{
  "working_branch": "main",
  "trigger_branch": "",
  "coding_agent_binary": "agent",
  "policy_profile": "balanced",
  "max_turns": 180
}
```

`policy_profile`: `advisory` | `balanced` | `strict` — governance enforcement level (default `balanced`).

**Response:**
```json
{
  "success": true,
  "output": [
    "   OK worker",
    "   OK orchestrator",
    "   OK worker: model configured",
    "   OK orchestrator: model configured",
    "   OK orchestrator: max_turns = 180",
    "   OK 'agent' found on PATH",
    "   coding_agent_binary: agent",
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

## `POST /api/plugins/kanban-advanced/update`

Updates settings in an already-initialized config. Writes to `kanban-config.yaml` and `.env`. Request body values for `working_branch`, `trigger_branch`, and `coding_agent_binary` are applied as submitted.

**Request:** Same shape as init.

**Response:** Same shape as init (re-runs materialization but skips profile creation). Optional overlay keys not in the managed set (e.g. `feature_branch_prefix`) are preserved.

## Error response

```json
{
  "error": "Descriptive error message"
}
```

Common errors:
- `"API unreachable"` — gateway not running
- `"Config file not found"` — attempting update before init
- `"hermes CLI not found on PATH"` — can't run init
