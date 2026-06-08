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
  "config_path": "/path/to/.hermes/kanban-overrides/kanban-config.yaml",
  "working_branch": "main",
  "coding_agent": "agent",
  "coding_agent_binary": "agent",
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

## `POST /api/plugins/kanban-advanced/init`

Runs the equivalent of `hermes kanban-advanced init --force` with the provided parameters.

**Request:**
```json
{
  "working_branch": "main",
  "coding_agent_binary": "agent",
  "max_turns": 180
}
```

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

Updates settings in an already-initialized config. Writes to `kanban-config.yaml` and `.env`.

**Request:** Same shape as init.

**Response:** Same shape as init (re-runs materialization but skips profile creation).

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
