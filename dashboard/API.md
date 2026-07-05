# Dashboard API

The Kanban-Advanced settings tab registers as a Hermes dashboard tab at `/kanban-advanced`
(positioned after the Skills tab). The UI is served from `dashboard/index.html` /
`dashboard/dist/index.js`; the backend routes live in `dashboard/plugin_api.py`.

> **Architecture note (Hermes ≥ v0.17.0):** Non-bundled plugins cannot auto-import Python
> API backends (GHSA-5qr3-c538-wm9j). The dashboard API runs as a standalone uvicorn server
> on `127.0.0.1:18900` (`scripts/dashboard_server.py`), started automatically during
> `hermes kanban-advanced init`. The frontend detects its environment and calls the sidecar
> directly (localhost) or via reverse proxy (remote/VPS). See `docs/reference/scripts.md`
> § Dashboard server for details.

Base path: `/api/plugins/kanban-advanced/`

All endpoints return JSON.

## `GET /api/plugins/kanban-advanced/status`

Returns current initialization state and config values.

**Query parameters (optional):**

| Param | Default | Meaning |
|-------|---------|---------|
| `probe` | `0` | When `1`, submits reachability probes to the background executor (legacy synchronous path). Normally probes are submitted via `POST /profiles/{profile}/probe` and `POST /coding-agent/probe` — the frontend uses these instead of `?probe=1` for async non-blocking loads. |
| `git_fetch` | `0` | When `1`, runs `git fetch origin` before computing `plugin_behind`. The frontend always calls this on every page load (cached for 5 min server-side). |

**Dashboard loading sequence (current behavior):**

1. `GET /status` — fast, returns cached probe results + `probed` flags
2. `POST /profiles/{profile}/probe` × N — submits profile probes to background executor (202 Accepted)
3. `POST /coding-agent/probe` — submits coding-agent CLI smoke to background executor (202 Accepted)
4. Frontend polls `GET /status` every 2s until all `probed` flags are `true` (max 90 attempts = 180s window)
5. `GET /status?git_fetch=1` — always runs; refreshes `plugin_behind` / update banner

**Probe architecture:**

- Probes run in a **single-threaded** `ThreadPoolExecutor` (max_workers=1) — serialized, never concurrent
- **Inter-probe cooldown:** 15s sleep between sequential probes so the gateway recovers between sessions
- **Profile probe timeout:** 120s (`hermes -p <profile> chat -q "say ok"`)
- **Coding-agent probe timeout:** 180s (`SMOKE_TIMEOUT_SECONDS` in `plugin/coding_agent.py`)
- **`probed` flag** (bool) on each profile and `coding_agent_cli` — `true` when a probe has been attempted (regardless of result value). Distinguishes "not probed yet" from "probed but inconclusive/timed out" — both produce `model_reachable: null`, but `probed: true` means the frontend can stop polling.
- Results are cached server-side: profiles 180s (`_TTL_MODEL_PROBE`), coding agent 180s. Cache format is `{reachable, detail}` for profiles, `{reachable, probed}` for coding agent.

**Response:**
```json
{
  "config_exists": true,
  "project_root": "/path/to/your/project",
  "config_path": "/path/to/.hermes/kanban-overrides/kanban-config.yaml",
  "working_branch": "main",
  "default_working_branch": "main",
  "trigger_branch": "",
  "coding_agent": "hermes",
  "coding_agent_binary": "hermes",
  "coding_agent_model": "auto",
  "coding_agent_cli": {
    "binary": "hermes",
    "display_name": "Hermes Agent",
    "on_path": true,
    "model": "auto",
    "model_label": "Auto (profile config)",
    "model_configured": true,
    "model_reachable": true,
    "probed": true,
    "supports_model_pick": true,
    "conflict": "",
    "conflict_hint": ""
  },
  "available_coding_binaries": [
    { "command": "hermes", "label": "hermes (Hermes Agent)", "product_key": "hermes", "contested": false },
    { "command": "cursor-agent", "label": "cursor-agent (Cursor CLI)", "product_key": "cursor", "contested": false }
  ],
  "policy_profile": "balanced",
  "notify_lifecycle": true,
  "notify_deliver": "",
  "notify_deliver_resolved": "discord",
  "walk_away_mode": false,
  "max_turns": 180,
  "profiles": {
    "kanban-advanced-orchestrator": {
      "exists": true,
      "has_model": true,
      "model": "anthropic/claude-opus-4.6",
      "provider": "openrouter",
      "model_reachable": true,
      "model_reachability_detail": "",
      "probed": true,
      "reasoning_effort": "high",
      "reasoning_effort_configured": true,
      "reasoning_effort_source": "agent",
      "recommended_reasoning_effort": "high"
    },
    "kanban-advanced-worker": {
      "exists": true,
      "has_model": true,
      "model": "anthropic/claude-sonnet-4.6",
      "provider": "openrouter",
      "model_reachable": true,
      "model_reachability_detail": "",
      "probed": true,
      "reasoning_effort": "medium",
      "reasoning_effort_configured": false,
      "reasoning_effort_source": "default",
      "recommended_reasoning_effort": "medium"
    }
  },
  "gateway": {
    "running": true,
    "outdated": false
  },
  "status_checks": {
    "probe": false,
    "git_fetch": false
  },
  "hermes_home": "/home/user/.hermes-state/my-app",
  "plugin_install_path": "/home/user/.hermes-state/my-app/plugins/kanban-advanced",
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

`profiles.*.model_reachable` reflects **Hermes** LLM backend reachability for orchestrator/worker sessions. When the probe has not yet run, `model_reachable` is `null` and `probed` is `false`. After probing: `true` = reachable (green dot), `false` = auth/model failure (yellow "model unreachable"), `null` with `probed: true` = timed out or inconclusive (yellow "configured"). `profiles.*.model_reachability_detail` may be `model not found`, `provider auth failed`, `inconclusive`, or `timed out (120s)`. `profiles.*.reasoning_effort` reflects `agent.reasoning_effort` from the profile `config.yaml` (or Hermes default `medium` when unset). `coding_agent_cli.model_reachable` reflects the **external coding CLI** smoke from project root — a green dot does not guarantee worktree dispatch (Cursor may still need `--trust` in the card worktree). Both fields populate when `probe=1`. **Save** and **Bootstrap** always run coding-CLI smoke when the binary is on PATH, regardless of `probe`.

`available_coding_binaries` lists supported commands currently on PATH for the **Binary on PATH** dropdown. When the configured binary is a contested shared name (e.g. `agent`), `coding_agent_cli.conflict` and `conflict_hint` are set — the dashboard shows a warning independent of reachability color. The plugin does not repair PATH; it surfaces operator direction only.

**Bootstrap limitation:** Init/Save smoke is **advisory** — HTTP 200 / successful init can return with `! coding CLI auth/model check failed` in `output`. Bootstrap writes `KANBAN_CODING_AGENT*` and `HOME` to `.env` but **does not** add vendor API keys. **Preflight** and **pre-dispatch gate** block decomposition when headless auth fails. See `plugin/data/references/coding-agent-auth.md`.

**Operator provisioning:** Init merges kanban paths into `.worktreeinclude` only — not application `.env`, `.venv/`, or `node_modules/`. See `plugin/data/references/operator-provisioning.md`.

Use `GET /api/plugins/kanban-advanced/coding-agent/models?binary=agent` to populate the dashboard coding-agent model picker. See `docs/reference/coding-agents.md` and `plugin/data/references/coding-agent-cli-invocation.md`.

Profile **reasoning effort** display and modal editing: [`docs/reference/dashboard-profile-reasoning.md`](../docs/reference/dashboard-profile-reasoning.md).

## `PUT /api/plugins/kanban-advanced/profiles/{profile_name}`

See [`docs/reference/dashboard-profile-reasoning.md`](../docs/reference/dashboard-profile-reasoning.md) for full contract.

Update a dispatch profile's Hermes model and/or `agent.reasoning_effort`. Writes via `hermes -p <profile> config set` (same durability as the Hermes dashboard model picker).

**Path:** `profile_name` must be a configured dispatch profile (`kanban-advanced-orchestrator` or `kanban-advanced-worker` by default).

**Request body** (JSON; at least one field required):

```json
{
  "provider": "openrouter",
  "model": "anthropic/claude-opus-4.6",
  "reasoning_effort": "high"
}
```

| Field | Behavior |
|-------|----------|
| `model` | Sets `model.default`. Requires `provider` when the profile has no existing provider. |
| `provider` | Sets `model.provider` (normalized to canonical Hermes provider IDs). |
| `reasoning_effort` | Sets `agent.reasoning_effort` (`none`, `low`, `minimal`, `medium`, `high`, `xhigh`). |

**Response 200:**

```json
{
  "ok": true,
  "profile": "kanban-advanced-orchestrator",
  "model": { "provider": "openrouter", "default": "anthropic/claude-opus-4.6" },
  "reasoning_effort": "high",
  "reasoning_effort_configured": true
}
```

**Errors:** `400` invalid body/level; `404` unknown or non-dispatch profile; `500` `hermes config set` failure (upgrade Hermes if `agent.reasoning_effort` is unsupported).

Invalidates cached `model_reachable` probe for that profile. Changes apply to **new** `hermes -p` sessions on that profile.

**Non-blocking:** The handler reads the JSON body in the async event loop, then delegates all
blocking config/subprocess work to `_execute_put_profile_settings()` which FastAPI runs in a
thread pool. The model probe fires immediately after — no queuing behind a blocked save.

When `config_exists` is false, the dashboard shows the bootstrap form.

The status banner shows **Initialized (Up-to-date)** or **Initialized (Update Plugin)** when `plugin_can_update` is true. **Update Plugin** calls `POST /api/plugins/kanban-advanced/update` (git pull in `plugin_install_path`, then re-materialize skills and cron scripts). On success the UI applies the response plugin-git fields immediately — it does **not** re-run `GET /status?git_fetch=1`. Disabled when up to date.

Use `project_root` to confirm the API resolved the correct repo (especially after `hermes update` or when multiple clones are on disk). If it points at the plugin install tree, set `KANBAN_PROJECT_ROOT` to your application repo before opening the tab.

## `POST /api/plugins/kanban-advanced/profiles/{profile_name}/probe`

Submits a model reachability probe for one dispatch profile to the background executor. Returns `202 Accepted` immediately — the probe runs asynchronously in the single-threaded executor. The frontend polls `GET /status` until `profiles.{profile_name}.probed` becomes `true`.

**Path:** `profile_name` must be a configured dispatch profile.

**Response 202:**
```json
{ "status": "queued", "profile": "kanban-advanced-orchestrator" }
```

Returns `"already_queued"` when a probe for this profile is already in-flight.

## `POST /api/plugins/kanban-advanced/coding-agent/probe`

Submits a coding-agent CLI smoke probe to the background executor. Same async contract as the profile probe — returns `202` immediately, frontend polls `GET /status` for `coding_agent_cli.probed`.

**Response 202:**
```json
{ "status": "queued", "profile": "hermes" }
```

Returns `"already_queued"` when a coding-agent probe is already in-flight.

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

Cursor uses `cursor-agent --list-models` or `agent --list-models`. Other supported binaries return curated defaults until a list command is wired in `plugin/coding_agent.py`.

## `POST /api/plugins/kanban-advanced/init`

Runs the equivalent of `hermes kanban-advanced init --force` with the provided parameters.

**Dispatch profiles:** Creates `kanban-advanced-orchestrator` and `kanban-advanced-worker` via `hermes profile create --no-skills`, installs `SOUL.md` from plugin prompts, seeds role-only profile skills (3 / 9), writes `.no-bundled-skills`, and verifies. Logs `HERMES_HOME:` and resolved profile paths in `output`. Sets `kanban.auto_decompose=false` and `kanban.dispatch_stale_timeout_seconds=14400` via `hermes config set`. See `wiki/bootstrap.md` and `plugin/data/references/dispatch-stale-timeout.md`.

**Re-init behavior:** If `kanban-config.yaml` already exists, `working_branch`, `trigger_branch`, and `policy_profile` are **preserved from the file** unless the request body includes overrides. First-time bootstrap uses form values. Bootstrap re-runs profile reconciliation (safe for fixing skill/SOUL drift). To change settings on an initialized project, edit fields and click **Save**. **Save** persists form values and also reconciles profiles. To update the plugin package itself, use **Update Plugin** on the tab.

**Request:**
```json
{
  "working_branch": "main",
  "trigger_branch": "",
  "coding_agent_binary": "hermes",
  "coding_agent_model": "auto",
  "policy_profile": "balanced",
  "notify_lifecycle": true,
  "notify_deliver": "",
  "notify_deliver_resolved": "discord",
  "walk_away_mode": false,
  "max_turns": 180
}
```

`coding_agent_model`: `auto` or a CLI-specific model ID (see `GET …/coding-agent/models`).

`policy_profile`: `advisory` | `balanced` | `strict` — governance enforcement level (default `balanced`).

`notify_lifecycle`: when `true` (default), execute/handoff (`kanban_handoff.py`) runs `provision_kanban_crons.sh --create`, which registers `kanban-lifecycle-notify-5m` with resolved home-channel deliver (not `local`); orchestrator decomposition verifies with `--check` only. **Dashboard Save** also reconciles crons (`--create` + `--check`) when lifecycle notify is on and the toggle or `notify_deliver` override changed — uses `.hermes/kanban/logs/lifecycle_plan_id` when present. Lifecycle messages print to stdout; Hermes cron deliver routes to the operator's configured home channel.

`notify_deliver`: optional overlay override (`telegram` | `discord` | `slack` | `signal` | `whatsapp` | `all` | `local`). Empty/absent → auto-resolve via `notify_deliver_resolved` in status (same order as `scripts/lib/resolve_notify_deliver.sh`). POST `/save` accepts `notify_deliver`; set to `""` or omit override to clear. Completion notify uses the same resolved deliver when `walk_away_mode` is on.

`walk_away_mode`: when `true`, `board_keeper.sh` runs unattended post-execution (reconciliation artifact, postmortem, archive, cleanup, completion notify) after final audit. Default `false` — orchestrator stops at post-execution checkpoints. See `plugin/data/references/walk-away-mode.md`.

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
    "   OK kanban-advanced-worker: 3 skills seeded [...] (.../profiles/kanban-advanced-worker)",
    "   OK Profiles verified: kanban-advanced-worker, kanban-advanced-orchestrator (role skills only)",
    "   OK 'hermes' found on PATH",
    "   coding_agent_binary: hermes",
    "   coding_agent_model: auto (Auto (profile config))",
    "   OK coding CLI reachable (Auto (profile config))",
    "   OK /path/to/kanban-config.yaml",
    "   OK 13 skills -> ...",
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
    "   OK 13 skills -> ...",
    "OK Plugin updated"
  ],
  "plugin_up_to_date": true,
  "plugin_behind": 0,
  "plugin_update_available": false,
  "plugin_local_changes": 0,
  "plugin_can_update": true
}
```

When already up to date, `unchanged` is `true` and pull is skipped. Successful responses always include `plugin_up_to_date: true` so the dashboard can show **Up-to-date** without a follow-up git fetch.

**Non-blocking:** The endpoint is defined as a regular `def` (not `async def`) so FastAPI runs
it in a thread pool. This prevents the git pull + materialize + profile reconcile from blocking
the event loop, which would starve the `/status` polling endpoint and cause the frontend terminal
log to appear stuck.

**Local changes in the install dir:**

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
