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
| `probe` | `0` | When `1`, run reachability probes on the slow path: (1) each **Hermes dispatch profile** via `hermes -p <profile> chat -q "say ok"`; (2) the **coding CLI** via `build_smoke_argv` / `smoke_test_coding_agent` (same contract as `scripts/coding_agent_invoke.sh smoke`). Skipped by default for fast tab loads. |
| `git_fetch` | `0` | When `1`, run `git fetch origin` before computing `plugin_behind`. Skipped by default; uses a short-lived server cache or local `rev-list` only. |

The dashboard loads **`/status`** first (fast), then **`/status?probe=1&git_fetch=1`** in the background when reachability has not yet passed this browser session. Returning to the tab reuses **sessionStorage**: if the last probe was **all green** (Hermes profile dots + coding CLI), subsequent tab loads skip `probe=1` and only refresh config/git fields via the fast path. Non-green or never-probed sessions always run the full probe. **Save**, **Bootstrap**, and **Update Plugin** invalidate session cache and re-probe.

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
    "kanban-advanced-orchestrator": {
      "exists": true,
      "has_model": true,
      "model": "anthropic/claude-opus-4.6",
      "provider": "openrouter",
      "model_reachable": true,
      "model_reachability_detail": "",
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

`profiles.*.model_reachable` reflects **Hermes** LLM backend reachability for orchestrator/worker sessions. When false, `profiles.*.model_reachability_detail` may be `model not found`, `provider auth failed`, or `inconclusive` — the dashboard labels this **model unreachable**, not coding-agent CLI auth. `profiles.*.reasoning_effort` reflects `agent.reasoning_effort` from the profile `config.yaml` (or Hermes default `medium` when unset). `coding_agent_cli.model_reachable` reflects the **external coding CLI** smoke from project root — a green dot does not guarantee worktree dispatch (Cursor may still need `--trust` in the card worktree). Both fields populate when `probe=1`. **Save** and **Bootstrap** always run coding-CLI smoke when the binary is on PATH, regardless of `probe`.

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

When `config_exists` is false, the dashboard shows the bootstrap form.

The status banner shows **Initialized (Up-to-date)** or **Initialized (Update Plugin)** when `plugin_can_update` is true. **Update Plugin** calls `POST /api/plugins/kanban-advanced/update` (git pull in `plugin_install_path`, then re-materialize skills and cron scripts). On success the UI applies the response plugin-git fields immediately — it does **not** re-run `GET /status?git_fetch=1`. Disabled when up to date.

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
  ],
  "plugin_up_to_date": true,
  "plugin_behind": 0,
  "plugin_update_available": false,
  "plugin_local_changes": 0,
  "plugin_can_update": true
}
```

When already up to date, `unchanged` is `true` and pull is skipped. Successful responses always include `plugin_up_to_date: true` so the dashboard can show **Up-to-date** without a follow-up git fetch.

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
