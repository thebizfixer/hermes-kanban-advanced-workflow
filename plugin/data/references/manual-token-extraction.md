# Manual token extraction (reconciliation fallback)

Use when `tokens.jsonl` / `token_tracker.py` is not wired. Prefer automated tracking when available.

## Extract from agent logs

```bash
# Cursor agent JSON output (dispatch with --output-format json)
grep -E '"usage"|"input_tokens"|"output_tokens"' "$WORKTREE/agent.log" 2>/dev/null | tail -20

# Codex / Claude: scan stderr for vendor usage blocks
grep -iE 'tokens?|usage' "$WORKTREE/agent.log" | tail -20
```

## Cost estimate (rough)

| Field | Source |
|-------|--------|
| Input tokens | Vendor JSON `usage.input_tokens` or log line |
| Output tokens | Vendor JSON `usage.output_tokens` |
| Model | `KANBAN_CODING_AGENT_MODEL` from `.env` / kanban-config |

Multiply by your provider $/1M rates for KPI tables in `kanban-reconciliation` — label estimates as **approximate**.

## KPI table template

| Card | Model | Input | Output | Est. USD | Notes |
|------|-------|-------|--------|----------|-------|
| `<task_id>` | | | | | dispatch exit code, retries |

## When to escalate

- No parseable usage after two dispatch attempts → note in reconciliation report; do not invent token counts.
