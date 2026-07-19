#!/usr/bin/env python3
"""Parse coding-agent stdout and append a token row to the JSONL log.

Handles two agent output modes:
  1. JSON with usage block (Cursor, Claude Code, Codex, Gemini, Grok)
     → exact token counts, source="agent"
  2. Text-only output (hermes, aider, unknown binaries)
     → estimated token counts from output size, source="estimated"

Always produces a token entry for dispatch runs so the evaluation chain
(E018 exact token gate) can attribute burn to the plan regardless of
which coding agent binary is configured.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from token_tracker import log_token_run  # noqa: E402


def _extract_usage(blob: dict) -> tuple[int, int, int, int, str]:
    """Extract token counts from a coding-agent JSON output blob.

    Handles both camelCase (Cursor) and snake_case (Claude Code) conventions.
    Checks blob.usage and blob.result.usage.
    """
    usage = blob.get("usage") or blob.get("result", {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    inp = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
    out = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
    cr = int(usage.get("cacheReadTokens") or usage.get("cache_read_tokens") or 0)
    cw = int(usage.get("cacheWriteTokens") or usage.get("cache_write_tokens") or 0)
    model = str(
        blob.get("model")
        or usage.get("model")
        or os.environ.get("KANBAN_CODING_AGENT_MODEL", "")
    )
    return inp, out, cr, cw, model


def _estimate_from_text(text: str) -> int:
    """Rough token estimate from UTF-8 byte count.

    Conservative: ~3.5 chars per token for code-heavy output.
    Always returns at least 1 so the eval chain sees non-zero activity.
    """
    byte_len = len(text.encode("utf-8", errors="replace"))
    return max(1, int(byte_len / 3.5))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--plan-id", default="", help="Plan ID for token attribution")
    args = parser.parse_args()

    # Resolve plan_id: CLI arg > KANBAN_PLAN_ID env > HERMES_KANBAN_PLAN_ID env
    plan_id = args.plan_id or os.environ.get("KANBAN_PLAN_ID", "") or os.environ.get("HERMES_KANBAN_PLAN_ID", "")

    path = Path(args.output_file)
    if not path.exists() or path.stat().st_size == 0:
        # No output captured — can't log anything
        return 0

    text = path.read_text(encoding="utf-8", errors="replace")

    # ── Try JSON extraction first ──────────────────────────────────────
    blob: dict = {}
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            blob = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    # plan_id already resolved at top of main() — use directly
    task_id = os.environ.get("HERMES_KANBAN_TASK", "")
    model = os.environ.get("KANBAN_CODING_AGENT_MODEL", "")

    if blob:
        inp, out, cr, cw, parsed_model = _extract_usage(blob)
        model = parsed_model or model
        if inp + out + cr + cw > 0:
            # Exact tokens from JSON usage block
            log_token_run(
                plan_id=plan_id,
                task_id=task_id,
                cursor_input_tokens=inp,
                cursor_output_tokens=out,
                cursor_cache_read_tokens=cr,
                cursor_cache_write_tokens=cw,
                cursor_model=model,
                source="agent",
                status="completed",
            )
            return 0

    # ── Fallback: text-only agent → estimated tokens ──────────────────
    estimated = _estimate_from_text(text)
    log_token_run(
        plan_id=plan_id,
        task_id=task_id,
        cursor_input_tokens=0,
        cursor_output_tokens=estimated,
        cursor_cache_read_tokens=0,
        cursor_cache_write_tokens=0,
        cursor_model=model,
        source="estimated",
        status="completed",
        extra={
            "estimation_method": "char_count",
            "output_chars": len(text),
            "output_bytes": len(text.encode("utf-8", errors="replace")),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
