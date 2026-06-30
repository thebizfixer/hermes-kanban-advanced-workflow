# Board Resolver Pattern

> **For subsystem authors:** Every script that queries kanban state must resolve its board — never assume "default."

## When to use

Any script that calls `hermes kanban list`, `hermes kanban show`, reads `kanban.db`, or accesses board-scoped data (tokens, scope violations, plan memory) must resolve the correct board first. The kanban-advanced plugin creates per-run timestamped boards (`kanban-standard-smoke-test-20260630-154500`) — the "default" board contains none of this data.

## API

### Python

```python
from scripts.lib.board_resolver import resolve_board_for_plan

board = resolve_board_for_plan("my-plan-id")
# Returns "my-plan-id-20260630-154500" or None

if board:
    subprocess.run(["hermes", "kanban", "--board", board, "list"])
else:
    subprocess.run(["hermes", "kanban", "list"])  # legacy fallback
```

### Bash (via CLI wrapper)

```bash
BOARD=$(python3 scripts/lib/resolve_board.py --plan-id "$PLAN_ID")
if [[ -n "$BOARD" ]]; then
    hermes kanban --board "$BOARD" list
else
    hermes kanban list  # legacy fallback
fi
```

## Discovery priority

1. `HERMES_KANBAN_BOARD` env var (explicit operator override)
2. Live board whose slug starts with sanitized plan_id (most recent timestamp first)
3. Archived board matching same prefix (most recent first)
4. `None` — caller chooses fallback (usually `"default"`)

## Design principle

The resolver is an **Encapsulated Service Locator** — consumers call `resolve_board_for_plan()` without knowing how discovery works internally. The anti-pattern is every subsystem re-implementing its own `grep`/`awk`/`glob` board discovery — which is exactly what existed before this module.

## Background

The kanban-advanced plugin uses **database-per-board isolation** (each timestamped board gets its own `kanban.db`). This is the strongest multi-tenancy isolation model. The tradeoff: you need a resolver to find the right database. This module fills that role.

## Related

- `smoke-test-gap-remediation` plan — 14 gaps identified, 6 traced to missing board scoping
- `board-resolver-singleton` plan — extracted this module from duplicated discovery logic
- `scripts/generate_postmortem.py:_board_db_path()` — original archived-board search (now delegates to resolver)
- `scripts/kanban_lifecycle_notify.sh` — first consumer of resolver in production
