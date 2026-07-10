# Dashboard Performance

Reference for operators and their agents. Documents expected UX timelines, cache architecture, and troubleshooting for "why is the dashboard slow?"

## Overview

The kanban-advanced dashboard tab is served by a standalone uvicorn sidecar process on `127.0.0.1:18900`. It provides a settings UI for configuring the plugin — profiles, coding agent, governance, and lifecycle toggles. Performance is dominated by hermes subprocess calls (4-5 per status refresh), which have been optimized with in-memory TTL caching and stale-while-revalidate patterns. A FastAPI lifespan handler pre-warms caches immediately on process start, so the first `/status` call returns in ~3s instead of 128s. Expected page load time: 2-5s initial, <1s subsequent visits.

## UX Timeline Matrix

| Scenario | Before (v0.18.0) | After (SWR + lifespan) | What changed |
|----------|-----------------|------------------------|-------------|
| First install → tab open | 2-15s until form, 22s-2min until badges | 2-5s until form, 22s-2min until badges | Lifespan pre-warms fast caches at startup; SWR caps gateway/git at ~0s |
| Sidecar crash → keepalive restart | 2-15s until form | 2-5s until form | Health endpoint triggers cache warming on first keepalive ping |
| Plugin update → form reappears | 13-17s | 13-17s | No change — update flow uses blocking path |
| Tab revisit (same session) | <1s | <1s | No change — all caches warm |
| Probe badge resolution | 22s-2min | 22s-2min | No change — probes are bound by LLM response time |

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
- `/status` — system health snapshot: profiles, gateway, coding agent, plugin git status, sidecar staleness. Gateway and git status use stale-while-revalidate (return cached or `None` immediately, refresh in background).
- `/health` — sidecar liveness: `{"status":"ok","pid":...,"started_at":...,"commit":"..."}`. Also triggers background cache warming on first call after sidecar start (belt-and-suspenders for crash recovery).
- `/profiles/{name}/probe` — enqueues a model reachability probe (202 Accepted, non-blocking)
- `/coding-agent/probe` — enqueues a coding agent CLI smoke test

**Lifespan pre-warming:** A FastAPI lifespan handler fires `_build_status(probe=False, git_fetch=False)` in a background thread at process start. By the time the user opens the dashboard tab (~15s), the in-memory caches for profiles, config, and coding-agent CLI are already warm. Git status populates via SWR background refresh within ~1s.

**Banner vs badges — separated:** The plugin update check (git fetch, sidecar staleness) resolves independently from profile model badges. The status banner updates to "Up-to-date" / "Update Plugin" / "Restart Plugin" as soon as git status is fetched (~15s with fetch, ~1s without). Profile badges ("reachable", "configured", "checking…") resolve in the background via probes and do not block the banner or the Update/Restart button.

**Probe lifecycle:**
1. Frontend submits probe requests (fire-and-forget, 202)
2. Backend `ThreadPoolExecutor(max_workers=1)` processes them serially
3. Each probe runs `hermes -p {profile} chat -q "say ok"` (120s timeout)
4. Result cached with 180s TTL, available on next `/status` call
5. Frontend polls `/status` at 3s intervals until all probes report `probed: true`

## Cache Architecture

All caches live in the sidecar process memory via `_cache_get`/`_cache_set` with monotonic timestamps. Invalidated on init, save, and update via `_invalidate_status_cache()`.

**Stale-while-revalidate (SWR):** The two slowest cache-miss paths — `_check_gateway()` (10s timeout on `hermes gateway status`) and `_git_behind_count()` with `fetch=True` (15s timeout on `git fetch origin`) — use an SWR pattern. On cache miss, they return `None` immediately and refresh in a background thread. The frontend shows "checking…" badges for `None` values. This caps `/status` response time at ~3s (fast caches) regardless of gateway/git state. Init and update flows pass `stale_ok=False` for blocking behavior when a real result is required.

| Cache Key | TTL | SWR? | What it caches | Invalidated by |
|-----------|-----|------|---------------|----------------|
| `git_behind:{path}` | 300s | Yes | Git commits behind upstream | TTL expiry + status cache clear |
| `model_reachable:{profile}` | 180s | No | Hermes LLM provider probe result | TTL expiry + status cache clear |
| `coding_agent_smoke:{binary}:{model}` | 180s | No | Coding CLI auth/model check | TTL expiry + status cache clear |
| `sidecar_stale` | 60s | No | Sidecar freshness vs plugin HEAD | TTL expiry + status cache clear |
| `gateway_status` | 30s | Yes | `hermes gateway status` result | TTL expiry + status cache clear |
| `hermes_profile_list` | 60s | No | `hermes profile list` output | TTL expiry + status cache clear |
| `default_working_branch:{root}` | 600s | No | Git branch detection result | TTL expiry + status cache clear |
| `_binaries_cache` (coding_agent.py) | 300s | No | Available coding binaries on PATH | `invalidate_coding_binaries_cache()` |

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
| `/status` takes >5s | Cold cache after sidecar restart — lifespan should have pre-warmed | Check `/health` was hit (keepalive cron triggers warming). Re-run init to recreate keepalive cron if missing. |
| Badges stuck on "checking…" >2min | Probe hung (slow LLM, auth timeout) or SWR background refresh stalled | Check `hermes gateway status`; restart gateway if outdated |
| Gateway / plugin status shows "checking…" persistently | SWR background refresh never completed (gateway down, git unreachable) | Check `hermes gateway status` and `git fetch origin` manually from plugin install dir |
| "Cannot reach API" banner | Sidecar crashed | Start manually: `python3 scripts/dashboard_server.py` |
| Gateway shows "not running" but actually is | SWR returned stale `None` before background refresh completed | Wait ~10s for background refresh. If persistent, gateway CLI may be slow — run `hermes gateway status` directly. |
| Coding agent shows "configured" not "reachable" | Probe hasn't completed or CLI auth broken | Check: `python3 scripts/check_coding_agent_cli.py` |

### 5. Force cache clear

```bash
# Restart the sidecar (clears all in-memory caches, lifespan auto-warms on restart)
curl -s http://127.0.0.1:18900/health | python3 -c "import sys,json; print(json.load(sys.stdin)['pid'])"
# Then: kill <pid> (keepalive cron auto-restarts within 60s, health ping triggers rewarming)
```

## Maintenance

- **TTLs use monotonic clock:** `time.monotonic()` — not affected by system clock changes
- **Invalidation hooks:** init, save, and update all call `_invalidate_status_cache()` which clears the server-side cache dict AND calls `invalidate_coding_binaries_cache()`
- **Module-level cache:** `get_available_coding_binaries()` cache lives in `plugin/coding_agent.py` — process-scoped, separate from the `_status_cache` dict
- **Lifespan pre-warming:** The FastAPI lifespan handler warms caches in a background thread at process start. The `/health` endpoint also triggers warming on first ping (belt-and-suspenders — keepalive cron hits `/health` every 60s after a crash restart)
- **Restarting the sidecar:** The keepalive cron (`kanban-dashboard-keepalive`) restarts within 60s of a crash. For manual restart, kill by PID (never use `taskkill /F /IM python.exe` on Windows — it kills the gateway too)
