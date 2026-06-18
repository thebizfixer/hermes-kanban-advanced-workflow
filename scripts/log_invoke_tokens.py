#!/usr/bin/env python3
"""Parse coding-agent JSON stdout and append infrastructure token row."""

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
    usage = blob.get("usage") or blob.get("result", {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    inp = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
    out = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
    cr = int(usage.get("cacheReadTokens") or usage.get("cache_read_tokens") or 0)
    cw = int(usage.get("cacheWriteTokens") or usage.get("cache_write_tokens") or 0)
    model = str(blob.get("model") or usage.get("model") or os.environ.get("KANBAN_CODING_AGENT_MODEL", ""))
    return inp, out, cr, cw, model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()
    text = Path(args.output_file).read_text(encoding="utf-8", errors="replace")
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
    if not blob:
        return 0
    inp, out, cr, cw, model = _extract_usage(blob)
    if inp + out + cr + cw == 0:
        return 0
    log_token_run(
        plan_id=os.environ.get("HERMES_KANBAN_PLAN_ID", ""),
        task_id=os.environ.get("HERMES_KANBAN_TASK", ""),
        cursor_input_tokens=inp,
        cursor_output_tokens=out,
        cursor_cache_read_tokens=cr,
        cursor_cache_write_tokens=cw,
        cursor_model=model,
        source="infrastructure",
        status="completed",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
