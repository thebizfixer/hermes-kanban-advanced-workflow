# Dependency graph format (decomposition)

ASCII dependency graph for orchestrator link planning before `hermes kanban link`.

## Template

```text
Plan: <plan_id>
Wave 0 (gate): [GATE-<plan_id>]
Wave 1 (parallel):
  [CARD-A] ──┐
  [CARD-B] ──┼──> [CARD-D]
  [CARD-C] ──┘
Wave 2:
  [CARD-D] --> [AUDIT-<plan_id>]
```

## Rules

- **Gate card** blocks all implementation children until orchestrator completes it after `validate_board.sh`.
- **Parent done** before child `ready` — use block-on-create + `auto_unblock.sh`, not `--triage`.
- Label nodes with **card title slug** or task id prefix from decomposition draft.
- Mark **goal-mode** cards with `(goal)` — max **2** per plan (`goal_card_budget`).

## Verify before create

- No orphan implementation cards without a parent path to GATE or root audit.
- Parallel lanes in the same wave must not edit the same `Files:` paths (P004 / split discipline).

## Card header fields (linking)

Each card block in the plan carries header fields that the orchestrator uses to build
the dependency graph. These fields support both YAML and markdown-bold syntax; the
parser normalizes values after extraction.

| Field | Accepted values | Normalized to | Behavior |
|---|---|---|---|
| `wave` | `1`, `2`, `3`… | `int` | Non-numeric values default to `1` |
| `wave_parent` | `card1`, `Card 1`, `none` | `"card1"` or `None` | `none` → no parent; `Card 1` → `card1` |
| `ordinal_parent` | same as `wave_parent` | same | Used when same-wave ordering matters |

**Normalization rules** (applied by `plan_parse.py`):

- `"none"` (any case) → `None` — card has no parent, links directly to gate.
- `"Card N"` / `"card N"` / `"cardN"` → `"cardN"` — lowercase key, no spaces.
- **Markdown bold**: `**Wave parent:** Card 1` parses identically to `wave_parent: Card 1`.
- **Human-readable titles**: `**Wave parent:** Card 2 — Persist` works fine — the parser
  extracts only the numeric card reference.

**Example card block header:**

```markdown
#### Card 2 — Persist quality_label
plan_id: extraction-quality-label-gap-20260709
wave: 2
wave_parent: Card 1
ordinal_parent: none
```

> After normalization: `wave=2`, `wave_parent="card1"`, `ordinal_parent=None`.
> The orchestrator links this card as: gate → card1 → card2.
