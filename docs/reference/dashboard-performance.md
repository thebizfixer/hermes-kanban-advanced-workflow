# Dashboard Performance

Reference for operators and their agents. Documents expected UX timelines, cache architecture, and troubleshooting for "why is the dashboard slow?"

## Overview

The kanban-advanced dashboard tab is served by a standalone uvicorn sidecar process on `127.0.0.1:18900`. It provides a settings UI for configuring the plugin — profiles, coding agent, governance, and lifecycle toggles. Performance is dominated by hermes subprocess calls (4-5 per status refresh), which have been optimized with in-memory TTL caching. Expected page load time after optimization: 2-15s initial, <1s subsequent visits.

## UX Timeline Matrix

| Scenario | Before (current) | After (optimized) | What changed |
|----------|-----------------|-------------------|-------------|
| First install → tab open | 7-22s until form, 70s-6min until badges | 2-15s until form, 22s-2min until badges | Cached hermes subprocesses, parallel status calls, removed probe cooldown |
| Plugin update → form reappears | 13-35s | 13-17s | Cached subprocesses survive restart warmup |
| Tab revisit (same session) | 5-10s | <1s | All caches warm |
| Probe badge resolution | 70s-6min | 22s-2min | No 15s inter-probe cooldown, reduced polling frequency |

## Architecture

The dashboard is served by a standalone uvicorn sidecar on `127.0.0.1:18900`. The frontend (Ink/React) calls the sidecar's FastAPI endpoints directly.

```
Browser (dashboard tab)
    │
    ├─ GET /api/plugins/kanban-advanced/status     ──→ sidecar (uvicorn:18900)
    ├─ GET /api/plugins/kanban-advanced/status?git_fetch=1
    ├─ POST /profiles/{name}/probe                  ──→ ThreadPoolExecutor (serial)
    ├─ POST /coding-agent/probe
    └─ GET /health (polling, restart detection)
```

**Key endpoints:**
- `/status` — system health snapshot: profiles, gateway, coding agent, plugin git status, sidecar staleness
- `/health` — sidecar liveness: `{"status":"ok","pid":...,"started_at":...,"commit":"..."}`
- `/profiles/{name}/probe` — enqueues a model reachability probe (202 Accepted, non-blocking)
- `/coding-agent/probe` — enqueues a coding agent CLI smoke test

**Banner vs badges — separated:** The plugin update check (git fetch, sidecar staleness) resolves independently from profile model badges. The status banner updates to "Up-to-date" / "Update Plugin" / "Restart Plugin" as soon as git status is fetched (~15s). Profile badges ("reachable", "configured", "checking…") resolve in the background via probes and do not block the banner or the Update/Restart button.

**Probe lifecycle:**
1. Frontend submits probe requests (fire-and-forget, 202)
2. Backend `ThreadPoolExecutor(max_workers=1)` processes them serially
3. Each probe runs `hermes -p {profile} chat -q "say ok"` (120s timeout)
4. Result cached with 180s TTL, available on next `/status` call
5. Frontend polls `/status` at 3s intervals until all probes report `probed: true`

## Cache Architecture

All caches live in the sidecar process memory via `_cache_get`/`_cache_set` with monotonic timestamps. Invalidated on init, save, and update via `_invalidate_status_cache()`.

| Cache Key | TTL | What it caches | Invalidated by |
|-----------|-----|---------------|----------------|
| `git_behind:{path}` | 300s | Git commits behind upstream | TTL expiry + status cache clear |
| `model_reachable:{profile}` | 180s | Hermes LLM provider probe result | TTL expiry + status cache clear |
| `coding_agent_smoke:{binary}:{model}` | 180s | Coding CLI auth/model check | TTL expiry + status cache clear |
| `sidecar_stale` | 60s | Sidecar freshness vs plugin HEAD | TTL expiry + status cache clear |
| `gateway_status` | 30s | `hermes gateway status` result | TTL expiry + status cache clear |
| `hermes_profile_list` | 60s | `hermes profile list` output | TTL expiry + status cache clear |
| `default_working_branch:{root}` | 600s | Git branch detection result | TTL expiry + status cache clear |
| `_binaries_cache` (coding_agent.py) | 300s | Available coding binaries on PATH | `invalidate_coding_binaries_cache()` |

**TTL tuning:** All TTLs are defaults for typical hardware (hermes subprocess ~1s). On slow machines (hermes >3s per call), increase TTLs proportionally. Constants live at the top of `dashboard/plugin_api.py`.

## Troubleshooting for Agents

When an operator asks "why is the dashboard slow?", walk through these diagnostic steps:

### 1. Check sidecar health

```bash
curl -s http://127.0.0.1:18900/health
# Expected: {"status":"ok","pid":...,"started_at":...,"commit":"..."}
# If connection refused: sidecar is down. Run: python3 scripts/dashboard_server.py
```

### 2. Measure /status latency

```bash
time curl -s http://127.0.0.1:18900/api/plugins/kanban-advanced/status > /dev/null
# Expected: <1.5s (warm cache), 2-5s (cold cache)
# If >5s: hermes subprocesses are slow. Check gateway health: hermes gateway status
```

### 3. Check probe status

```bash
curl -s http://127.0.0.1:18900/api/plugins/kanban-advanced/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p, info in d.get('profiles', {}).items():
    print(f'{p}: probed={info.get(\"probed\")}, reachable={info.get(\"model_reachable\")}')
cli = d.get('coding_agent_cli', {})
print(f'coding_agent: probed={cli.get(\"probed\")}, reachable={cli.get(\"model_reachable\")}')
"
```

### 4. Common causes of slowness

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `/status` takes >5s | Cold cache after sidecar restart | Wait 30s for caches to warm, or run `/status` twice |
| Badges stuck on "checking…" >2min | Probe hung (slow LLM, auth timeout) | Check `hermes gateway status`; restart gateway if outdated |
| "Cannot reach API" banner | Sidecar crashed | Start manually: `python3 scripts/dashboard_server.py` |
| Gateway shows "not running" but actually is | 30s cache window | Wait for TTL expiry or restart sidecar to clear caches |
| Coding agent shows "configured" not "reachable" | Probe hasn't completed or CLI auth broken | Check: `python3 scripts/check_coding_agent_cli.py` |

### 5. Force cache clear

```bash
# Restart the sidecar (clears all in-memory caches)
curl -s http://127.0.0.1:18900/health | python3 -c "import sys,json; print(json.load(sys.stdin)['pid'])"
# Then: kill <pid> (keepalive cron auto-restarts within 60s)
```

## Maintenance

- **TTLs use monotonic clock:** `time.monotonic()` — not affected by system clock changes
- **Invalidation hooks:** init, save, and update all call `_invalidate_status_cache()` which clears the server-side cache dict AND calls `invalidate_coding_binaries_cache()`
- **Module-level cache:** `get_available_coding_binaries()` cache lives in `plugin/coding_agent.py` — process-scoped, separate from the `_status_cache` dict
- **Restarting the sidecar:** The keepalive cron (`kanban-dashboard-keepalive`) restarts within 60s of a crash. For manual restart, kill by PID (never use `taskkill /F /IM python.exe` on Windows — it kills the gateway too)
