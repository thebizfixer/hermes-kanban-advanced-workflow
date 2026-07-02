# Hermes v0.18.0 upgrade notes

> **Last updated:** 2026-07-01 · **Hermes version:** v0.18.0 (v2026.7.1)
> **Plugin version:** v0.9.0 · **Tested on:** Windows 10 (git-bash/MSYS)

This document records every v0.18.0 change that affects the kanban-advanced plugin.

---

## ✅ Beneficial: Kanban lifecycle hooks become native

### What changed

v0.18.0 ships three kanban lifecycle plugin hooks (#50349):
- `kanban_task_claimed` — dispatcher-side, before worker spawn
- `kanban_task_completed` — worker-side, carries `summary`
- `kanban_task_blocked` — worker-side, carries `reason`

Each fires **after** the DB write txn commits, carries `profile_name` from
`HERMES_HOME`, and is failure-safe (a raising hook never breaks the board).

### How we adapted

The plugin previously used `post_tool_call` to detect `kanban_complete` and
trigger `auto_unblock`. This was fragile — it depended on tool-name matching
and result-string inspection. The new `kanban_task_completed` hook fires on
the exact lifecycle event with structured kwargs, and `kanban_task_blocked`
provides a native block-event log entry.

- `plugin/hooks.py` — added `on_kanban_task_completed()` and
  `on_kanban_task_blocked()`. Removed auto_unblock trigger from
  `post_tool_call` (which still logs all tool calls to JSONL).
- `plugin/__init__.py` — registered both hooks.
- `plugin.yaml` — declared both in `provides_hooks`.
- `scripts/smoke_test_plugin.py` — updated `EXPECTED_HOOKS`.

---

## ✅ Additive: Typed block reasons (`block_kind`)

### What changed

`block_task()` gained a `kind` parameter (`dependency | needs_input |
capability | transient`, #52848). The `hermes kanban block` CLI gained
`--kind`. Omission defaults to legacy NULL-kind behavior.

### How we adapted

- `plugin/schemas.py` — added `kind` param (optional, same enum) to
  `KANBAN_BLOCK` schema.
- `plugin/tools.py` — `kanban_block()` forwards `--kind` when present.

Backward-compatible: existing calls without `kind` fall through to legacy
single-block behavior.

---

## ⚠️ Behavior change: `unblock_task` no longer resets `block_recurrences`

In v0.18.0, `unblock_task` deliberately does **not** reset the
`block_recurrences` counter (#52848). Only `complete_task` clears it. This
prevents the infinite unblock↔re-block loop. At
`BLOCK_RECURRENCE_LIMIT` (patched to 5 by the plugin), same-cause re-blocks
escalate to `triage`.

**Impact on plugin:** The `auto_unblock.sh` script unblocks children when
their parents complete — this is the correct trigger. It does not interfere
with recurrence tracking. No changes needed.

---

## ✅ Profile detection in hook kwargs

v0.18.0 adds `ctx.profile_name` on `PluginContext` (#50346), and the kanban
lifecycle hooks resolve `profile_name` from `HERMES_HOME` automatically.
`on_session_start` also receives `profile_name` in its kwargs from the
plugin invoker. The old `HERMES_PROFILE` env-var fallback in `_get_profile()`
remains as a safety net.

---

## ℹ️ Multi-board awareness (deferred)

v0.18.0 supports multiple isolated kanban boards under
`~/.hermes/kanban/boards/<slug>/`. Workers are pinned via
`HERMES_KANBAN_BOARD`. The plugin currently operates on the `default` board
only — multi-board support is deferred to v1.1.0. Single-board users see no
change.

---

## ℹ️ Cron continuations (beneficial, no action)

Cron jobs can now be `attach_to_session: true` for continuable delivery
(#52250). The plugin's lifecycle crons (`board_keeper`, `auto_unblock`) are
fire-and-forget — no change needed. New `attach_to_session` is opt-in.

---

## ℹ️ Verification / completion contracts (aligned, no action)

v0.18.0 adds coding verification evidence and `/goal` completion contracts
(#50501). The plugin's evaluation chain (`kanban_evaluation_chain.py`) and
pre-complete gate (`kanban_pre_complete_gate.py`) already enforce
verification before `kanban_complete`. Complementary — no changes needed.

---

## ℹ️ Backup includes kanban boards

Pre-update snapshots now include `projects.db` and kanban boards (#52990).
Beneficial — no action needed.

---

**All code remediations complete.** Remaining items: run `hermes update`
manually, then `hermes plugins sync kanban-advanced`.
