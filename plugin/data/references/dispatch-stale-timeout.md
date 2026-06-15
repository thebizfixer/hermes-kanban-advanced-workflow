# dispatch_stale_timeout_seconds (Hermes kanban config)

> **SSOT** for why kanban-advanced sets `kanban.dispatch_stale_timeout_seconds` to **14400** (4 hours) at bootstrap.

## What it does

Hermes reclaims tasks stuck in `running` when they have **no heartbeat** for longer than this threshold (seconds). Setting **`0`** disables stale reclaim entirely.

**Location:** Hermes `config.yaml` via `hermes config` — **not** `.hermes/kanban-overrides/kanban-config.yaml`.

```bash
hermes config get kanban.dispatch_stale_timeout_seconds
hermes config set kanban.dispatch_stale_timeout_seconds 14400
```

## Why 14400

kanban-advanced does **not** tune this from benchmarks in-repo. **14400** is the value we set because:

1. **Matches Hermes kanban documentation** (commonly described as a 4-hour default) while upstream runtime may still behave like **`0` (disabled)** ([#35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 7).
2. **Bootstrap turns the safety net on** — without an explicit set, orphaned `running` cards can persist indefinitely after crashes or gateway loss.
3. **Healthy work stays far below 4h** — workers are required to heartbeat every **~3 minutes** during agent execution; the orchestrator skill describes 4h as well above that cadence.
4. **Long plans are not capped at 4h** — multi-hour walk-away runs are fine as long as heartbeats continue; only **hours without heartbeat** trigger reclaim.

## Layered timers (do not conflate)

| Layer | Typical value | Role |
| --- | --- | --- |
| Worker heartbeat | ~3 min | Keeps active cards alive during coding-agent work |
| Short dispatcher reclaim | ~15 min idle | First recovery when heartbeat is forgotten |
| `dispatch_stale_timeout_seconds` | **14400 (4h)** | Longer zombie/orphan net (crash before first heartbeat, killed process, gateway died) |
| Coding CLI per invoke | `timeout 900` | Single agent subprocess cap (~15 min); retries can extend wall clock |

## What 14400 does **not** fix

- **Thrash** — worker heartbeats but makes no progress ([#35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 1). Plugin answer: `board_keeper.sh` event-count / iteration budget.
- **OAuth parallel stampede** — plugin answer: gate prewarm, `auto_unblock` stagger, auth lock file.
- **Task duration SLA** — 14400 is not “finish every card in 4 hours.”

## Bootstrap behavior

`hermes kanban-advanced init` and dashboard **Bootstrap** call `plugin/hermes_kanban_bootstrap.py`, which sets:

- `kanban.auto_decompose = false`
- `kanban.dispatch_stale_timeout_seconds = 14400`

Failures are **advisory** in bootstrap output (same pattern as `auto_decompose`) — init can still succeed; re-run init or set manually if `hermes config set` fails.

Preflight emits a **degraded** warning when the value is `0` or unreadable.

## Upstream default changes

If a future Hermes release fixes the runtime default to match documentation (non-zero stale timeout), kanban-advanced can drop the explicit `config set` or lower bootstrap to a no-op when the effective value is already ≥ 14400. Until then, bootstrap **always** sets **14400** explicitly.

## Cross-references

- Operator table: [wiki/configuration.md](../../../wiki/configuration.md) § Hermes v0.15.x kanban config keys
- Upstream gap: [wiki/troubleshooting.md](../../../wiki/troubleshooting.md) § Upstream Hermes constraints
- Worker heartbeat: `kanban-advanced:kanban-worker` Step 3 / Step 4
