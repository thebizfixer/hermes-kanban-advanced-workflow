# Hermes v0.17.0 upgrade notes

> **Last updated:** 2026-06-25 · **Hermes version:** v0.17.0 (v2026.6.19, commit d6269da7)
> **Plugin version:** v0.9.0 · **Tested on:** Windows 10 (git-bash/MSYS)

This document records every v0.17.0 change that affects the kanban-advanced plugin — confirmed breakage, new behaviour, and remediation steps. Update it after every Hermes upgrade that touches plugins, kanban, cron, delegation, or the CLI.

---

## ⚠️ Breaking: Plugin fails to load — namespace-based loading

### What changed

v0.17.0 loads directory-based plugins as **namespace packages** under `hermes_plugins.<slug>`. The plugin's root `__init__.py` is loaded as `hermes_plugins.kanban_advanced`, and its `plugin/` subdirectory becomes `hermes_plugins.kanban_advanced.plugin`. This is a deliberate architectural change — bundled plugins in the Hermes repo were already updated, but the developer docs do not mention it.

### How we break

The plugin uses **9 absolute imports** of the form `from plugin.<module> import ...` across its internal modules. These resolve when the plugin runs from its own working directory (where `plugin/` is a top-level package), but fail under the `hermes_plugins.kanban_advanced` namespace because `plugin` is no longer on `sys.path` as a top-level name.

**Error at startup:**
```
Failed to load plugin 'kanban-advanced': No module named 'plugin'
  File "...\kanban-advanced\plugin\__init__.py", line 5, in <module>
  File "...\kanban-advanced\plugin\cli.py", line 45, in <module>
  File "...\kanban-advanced\plugin\coding_agent.py", line 16, in <module>
```

### Affected imports (9 instances)

| File | Line | Import |
|------|------|--------|
| `plugin/coding_agent.py` | 16 | `from plugin.coding_agent_env import (...)` |
| `plugin/coding_agent.py` | 479 | `from plugin.hermes_model_config import read_active_model_config` |
| `plugin/config_overlay.py` | 466 | `from plugin.hermes_notify_deliver import resolve_notify_deliver as _resolve` |
| `plugin/config_overlay.py` | 530 | `from plugin.coding_agent_env import dispatch_runtime_env_updates` |
| `plugin/config_overlay.py` | 596 | `from plugin.coding_agent import normalize_coding_agent_model` |
| `plugin/config_overlay.py` | 625 | `from plugin.coding_agent import normalize_coding_agent_model` |
| `plugin/hooks.py` | 56 | `from plugin.hermes_gateway_home import resolve_gateway_hermes_home` |
| `plugin/script_materialize.py` | 10 | `from plugin.file_text import read_utf8_text` |
| `plugin/worktree_provision.py` | 8 | `from plugin.config_overlay import read_overlay_config, resolve_hermes_home` |

### Remediation

Replace each with the equivalent relative import. Example:

```python
# Before (broken in v0.17.0)
from plugin.coding_agent_env import (
    AUTH_PROFILES,
    ensure_coding_agent_runtime_env,
)

# After (works in v0.17.0)
from .coding_agent_env import (
    AUTH_PROFILES,
    ensure_coding_agent_runtime_env,
)
```

For cross-subpackage imports (e.g. `config_overlay.py` importing from `coding_agent.py`), use `from ..plugin.coding_agent import ...` or restructure to avoid the `plugin.` prefix entirely.

### Upstream context

- The namespace constant is `_NS_PARENT = "hermes_plugins"` in `hermes_cli/plugins.py:199`
- The loading method is `_load_directory_module()` at `plugins.py:1645`
- Bundled plugins (e.g. `google_chat`) already include comments acknowledging the namespace
- **No GitHub issue exists** for third-party plugin absolute-import breakage as of 2026-06-25
- **No migration guide** on hermes-agent.nousresearch.com mentions this change

---

## ❌ Removed: `hermes send_message` CLI

### What changed

PR [#47856](https://github.com/NousResearch/hermes-agent/pull/47856) removed the agent-callable `send_message` tool. The `hermes send_message` CLI subcommand is also gone (it was tied to the same tool registry entry). The underlying send engine is preserved — `hermes send` is the replacement.

### What breaks

`scripts/kanban_completion_notify.sh:96-97` calls `hermes send_message` for walk-away completion notifications. These calls silently fail (exit code 2, "invalid choice").

### Remediation

Replace with `hermes send` using the `--to` flag:

```bash
# Before (broken)
hermes send_message "$MSG" --deliver "$DELIVER"

# After
hermes send "$MSG" --to "$DELIVER"
```

Note: `hermes send` uses `--to` (not `--deliver`) and the target format may differ. Test with the resolved deliver target before deploying.

### Upstream context

- The `messaging` toolset was also removed from `_HERMES_CORE_TOOLS` — config files referencing it may produce "Unknown toolsets: messaging" warnings (upstream bug [#52382](https://github.com/NousResearch/hermes-agent/issues/52382), multiple community PRs open)
- Gateway kanban notifier (used by lifecycle hooks) is explicitly preserved in `GatewayKanbanWatchersMixin`

---

## ⚠️ Missing: Dashboard keepalive cron

### What changed

The keepalive cron (`kanban-dashboard-keepalive`) is normally created during `hermes kanban-advanced init`. Since the init CLI is broken (see above), the cron is not created after plugin update or fresh install. The sidecar has no crash recovery until the cron is manually provisioned.

### Remediation

```bash
# Create the keepalive cron (idempotent)
hermes cron create "every 1m" \
  --name kanban-dashboard-keepalive \
  --no-agent \
  --script dashboard_server_keepalive.py \
  --deliver local \
  --repeat 999
```

Note: The `.py` launcher is preferred over the `.sh` version on Windows (avoids Hermes bug [#23404](https://github.com/NousResearch/hermes-agent/issues/23404) — bash backslash path mangling). However, `script_materialize.py` currently only syncs `dashboard_server_keepalive.sh` (line 31), not the `.py` launcher. This is a separate gap — see § Materialization gap below.

---

## ⚠️ Materialization gap: `.py` keepalive not synced

`plugin/script_materialize.py` line 31 lists `dashboard_server_keepalive.sh` but not `dashboard_server_keepalive.py`. On Windows, `.sh` scripts run through the cron runner suffer from backslash path mangling (Hermes #23404). The `.py` launcher uses `subprocess.run(shell=True, MSYS paths)` and avoids this.

### Remediation

Add `"dashboard_server_keepalive.py"` to the `HERMES_SCRIPT_NAMES` tuple in `plugin/script_materialize.py:14-32`.

---

## 🔄 New kanban features (no immediate breakage, worth understanding)

### Auto-subscribe on `kanban_create` (PR [#48635](https://github.com/NousResearch/hermes-agent/pull/48635))

Workers auto-subscribe to their own task completion/block events. Gated by `kanban.auto_subscribe_on_create` in `config.yaml` (default `true`). **Positive for the plugin** — reduces explicit subscribe overhead. Set to `false` to keep the old explicit-subscribe behaviour.

### Toolset pinning for assigned profiles (PR [#45590](https://github.com/NousResearch/hermes-agent/pull/45590))

Hermes now auto-pins toolsets based on the assigned worker profile. Verify that the plugin's profile bootstrap (`plugin/profile_bootstrap.py`) doesn't conflict — the plugin sets worker toolsets explicitly and this may need reconciliation.

### Machine-global dispatcher singleton lock (PR [#49068](https://github.com/NousResearch/hermes-agent/pull/49068))

Only one dispatcher runs across all gateway instances. **No impact** on the plugin's single-gateway deployment model.

### Hold reclaim while worker still alive (PR [#49064](https://github.com/NousResearch/hermes-agent/pull/49064))

Prevents premature task reclaim when a worker process is still running. **Positive for the plugin** — reduces false-positive stale detections.

---

## 🔄 Delegation: wall-clock timeout removed

The default subagent wall-clock timeout was removed in v0.17.0. The plugin uses its own domain-specific timeouts in `subagent_gate.timeouts` (plan: 30s, env: 120s, infra: 15s) — these are unaffected. The parallel subagent gate's E022 fallback still works.

---

## 🔄 Config migration: `kanban.auto_subscribe_on_create` not in current config

New kanban config options are set to defaults but don't appear in `hermes config show` output. Run `hermes config migrate` to pull them into `config.yaml` explicitly.

Also: `messaging` toolset removal may cause "Unknown toolsets" warnings if any profile config references it. The plugin does not directly reference `messaging`, but user profiles might.

---

## ✅ Unaffected subsystems (verified working)

| Subsystem | Verified | Notes |
|-----------|----------|-------|
| Kanban board (`list`, `create`, `complete`, `dispatch`) | ✅ | Tested live |
| Gateway kanban notifier | ✅ | Preserved in `GatewayKanbanWatchersMixin` |
| Wave crons (auto-unblock, board-keeper, lifecycle) | ✅ | All 3 running, delivering |
| Dashboard sidecar server | ✅ | API healthy once started manually |
| Profile builder (new dash feature) | ✅ | No conflict with plugin bootstrap |
| Tool API changes (memory batch, search_files, read_file, image_generate) | ✅ | Plugin doesn't call these directly |

---

## 📋 Documentation stale references

88 references to `hermes kanban-advanced init` across the repo (docs, README, AGENTS.md, wiki, tutorials, dashboard). If the CLI invocation path changes permanently (e.g. to `python3 plugin/cli.py init` or a new `hermes` subcommand registration pattern), all must be updated.

---

## 🔗 Related upstream issues

| Issue | Title | Status |
|-------|-------|--------|
| [#27548](https://github.com/NousResearch/hermes-agent/issues/27548) | Platform plugin discovery drops namespace from keys | Fixed |
| [#28138](https://github.com/NousResearch/hermes-agent/issues/28138) | Gateway log filter excludes `hermes_plugins.*` loggers | Open |
| [#40101](https://github.com/NousResearch/hermes-agent/issues/40101) | Third-party memory plugin not discoverable via entry points | Open (P3) |
| [#47856](https://github.com/NousResearch/hermes-agent/pull/47856) | Remove agent-callable `send_message` tool | Merged |
| [#48635](https://github.com/NousResearch/hermes-agent/pull/48635) | Auto-subscribe on `kanban_create` | Merged |
| [#52382](https://github.com/NousResearch/hermes-agent/issues/52382) | "Unknown toolsets: messaging" warning | Open |

---

## Remediation priority

1. ~~Fix 9 absolute imports~~ → **Resolved.** Dual-path import strategy in `script_materialize.py`; all other imports converted to relative.
2. ~~Fix `kanban_completion_notify.sh`~~ → **Resolved.** Uses `hermes send --to` since 2026-06-25.
3. ~~Add `.py` keepalive to materialization list~~ → **Resolved.** `dashboard_server_keepalive.py` added to `HERMES_SCRIPT_NAMES` at line 41.
4. **Run `hermes config migrate`** → pull in `kanban.auto_subscribe_on_create` and other new defaults (operational, not a code fix)
5. **Update 88 doc references** → if CLI invocation path changes permanently (not yet; `hermes kanban-advanced init` still works)

**All code-level remediations are complete.** The plugin is v0.17.0-compatible. Remaining items are operational (config migrate) or contingent on future upstream changes.
