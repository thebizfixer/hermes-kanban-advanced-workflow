# Hermes v0.15.x–0.16.x upgrade notes

This bundle requires **Hermes Agent ≥ 0.16.0** (test target: 0.17.0). Goal-mode cards (`--goal` on `hermes kanban create`) require at least 0.15.2 upstream; 0.16.0 is the supported floor for kanban-advanced.

## Commands

| Older | Current |
| --- | --- |
| `hermes config get` | `hermes config show` |

## Kanban

- Worktree workspaces must use **absolute** paths: `worktree:/tmp/wt-<plan>-<card>`.
- `hermes kanban block` applies to `ready` tasks, not `todo`.
- **Goal-mode cards (0.15.2+):** `hermes kanban create "…" --goal [--goal-max-turns N]` — same Ralph-style judge loop as `/goal`, using card title + body as acceptance criteria. See [goal-card-selection.md](goal-card-selection.md) and [docs/how-to/goal-cards.md](../docs/how-to/goal-cards.md). Default turn budget: 20 (`goals.max_turns` in `config.yaml`).

## Persistent goals (`/goal`)

Session-level standing goals (CLI and gateway): `/goal <text>`, `/goal status`, `/goal pause`, `/goal resume`, `/goal clear`, `/subgoal`. Documented upstream: [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals). On kanban-advanced boards, prefer **decomposed one-shot cards**; use `--goal` on a card only when the plan marks `goal_card: true` during Harden (0–2 per plan).

## Gateway

After SQLite `torn-extend` errors: `hermes gateway restart`, then re-run preflight DB integrity.

Upgrade Hermes before bumping `bundle_version` in your overlay.
