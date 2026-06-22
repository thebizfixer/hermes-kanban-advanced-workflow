#!/usr/bin/env python3
"""Token metering via Hermes insights — authoritative, not self-reported.

Queries 'hermes insights' before and after a coding-agent dispatch to
compute the exact token delta. Since Hermes records tokens from provider
response headers (not from agent output), this is non-self-reporting.

Usage:
    python3 hermes_token_meter.py snapshot          # capture baseline
    python3 hermes_token_meter.py delta             # compute delta vs baseline
    python3 hermes_token_meter.py meter <command>   # snapshot, run command, delta

The computed delta is appended to the kanban token log so the evaluation
chain (E018) can attribute exact token burn without depending on the
coding agent's self-reported output.
"""

from __future__ import annotations

import argparse
import json
import os

import os
from pathlib import Path as _P
def _get_coding_agent_binary():
    for base in (_P.cwd(), _P.home()):
        cfg = base / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
        if cfg.exists():
            try:
                for line in open(cfg):
                    if "coding_agent_binary:" in line:
                        v = line.split(":", 1)[1].strip().replace('"', '').replace("'", '')
                        if v: return v
            except: pass
    return os.environ.get("KANBAN_CODING_AGENT") or "hermes"
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from token_tracker import log_token_run  # noqa: E402

BASELINE_FILE = Path(tempfile.gettempdir()) / "hermes_token_meter_baseline.json"


def _parse_insights(text: str) -> dict:
    """Parse 'hermes insights' output into structured data."""
    import re

    result: dict = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "sessions": 0,
        "model_tokens": {},
    }

    m = re.search(r"Input tokens:\s+([\d,]+)", text)
    if m:
        result["input_tokens"] = int(m.group(1).replace(",", ""))

    m = re.search(r"Output tokens:\s+([\d,]+)", text)
    if m:
        result["output_tokens"] = int(m.group(1).replace(",", ""))

    m = re.search(r"Total tokens:\s+([\d,]+)", text)
    if m:
        result["total_tokens"] = int(m.group(1).replace(",", ""))

    m = re.search(r"Sessions:\s+(\d+)", text)
    if m:
        result["sessions"] = int(m.group(1))

    # Per-model token breakdown
    for m in re.finditer(
        r"(\S+)\s+(\d+)\s+([\d,]+)", text.split("Models Used")[-1].split("Platforms")[0]
    ):
        model = m.group(1).strip()
        if model and not model.startswith("Model") and not model.startswith("──"):
            result["model_tokens"][model] = int(m.group(3).replace(",", ""))

    return result


def snapshot() -> int:
    """Capture current Hermes token state as baseline."""
    result = subprocess.run(
        ["hermes", "insights", "--days", "1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        print(f"[token_meter] ERROR: hermes insights failed: {result.stderr[:200]}")
        return 1

    state = _parse_insights(result.stdout)
    state["timestamp"] = time.time()
    state["snapshot_session_count"] = state.pop("sessions", 0)

    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(state, indent=2))
    print(
        f"[token_meter] Baseline: {state['total_tokens']:,} total tokens "
        f"({state['input_tokens']:,} in / {state['output_tokens']:,} out)"
    )
    return 0


def delta(
    plan_id: str = "",
    task_id: str = "",
    source: str = "hermes_insights",
) -> int:
    """Compute token delta since last snapshot and log to token tracker."""
    if not BASELINE_FILE.exists():
        print("[token_meter] ERROR: no baseline snapshot — run 'snapshot' first")
        return 1

    try:
        before = json.loads(BASELINE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        print("[token_meter] ERROR: corrupt baseline file")
        return 1

    result = subprocess.run(
        ["hermes", "insights", "--days", "1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        print(f"[token_meter] ERROR: hermes insights failed: {result.stderr[:200]}")
        return 1

    after = _parse_insights(result.stdout)

    inp_delta = max(0, after["input_tokens"] - before.get("input_tokens", 0))
    out_delta = max(0, after["output_tokens"] - before.get("output_tokens", 0))
    total_delta = max(0, after["total_tokens"] - before.get("total_tokens", 0))
    new_sessions = max(0, after.get("sessions", 0) - before.get("snapshot_session_count", 0))

    # Sanity check: if delta seems wrong (concurrent sessions), warn but still log
    if new_sessions > 1:
        print(
            f"[token_meter] WARNING: {new_sessions} new sessions since snapshot — "
            f"token delta may include activity from other sessions"
        )

    if total_delta == 0:
        print(
            "[token_meter] WARNING: No token delta detected — dispatch may not have "
            "produced measurable token activity (or insights window rolled). "
            "Logging zero-delta entry for audit trail."
        )

    plan_id = plan_id or os.environ.get("HERMES_KANBAN_PLAN_ID", "")
    task_id = task_id or os.environ.get("HERMES_KANBAN_TASK", "")

    # Log even zero-delta so we have an audit trail (proves metering ran)
    binary = _get_coding_agent_binary()
    log_token_run(
        plan_id=plan_id,
        task_id=task_id,
        cursor_input_tokens=inp_delta,
        cursor_output_tokens=out_delta,
        cursor_cache_read_tokens=0,
        cursor_cache_write_tokens=0,
        cursor_model=os.environ.get("KANBAN_CODING_AGENT_MODEL", ""),
        # Also populate hermes bucket for neutrality when config is hermes
        hermes_total=inp_delta + out_delta if "hermes" in binary.lower() else 0,
        source=source,
        status="completed" if total_delta > 0 else "no_delta",
        extra={
            "coding_agent_binary": binary,
            "metering_method": "hermes_insights_delta",
            "before_total": before.get("total_tokens", 0),
            "after_total": after["total_tokens"],
            "new_sessions": new_sessions,
        },
    )

    if total_delta == 0:
        return 0

    print(
        f"[token_meter] Delta: {total_delta:,} total tokens "
        f"({inp_delta:,} in / {out_delta:,} out) "
        f"— logged as source={source}"
    )
    return 0


def meter_command(
    argv: list[str],
    plan_id: str = "",
    task_id: str = "",
    source: str = "hermes_insights",
) -> int:
    """Snapshot, run a command, compute delta — all in one call."""
    # Snapshot
    if snapshot() != 0:
        return 1

    # Run the command
    print(f"[token_meter] Running: {' '.join(argv)}")
    rc = subprocess.call(argv)
    if rc != 0:
        print(f"[token_meter] Command exited with code {rc}")

    # Delta
    delta(plan_id=plan_id, task_id=task_id, source=source)

    return rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes token metering via insights delta"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("snapshot", help="Capture current token baseline")

    dp = sub.add_parser("delta", help="Compute delta vs baseline and log")
    dp.add_argument("--plan-id", default="")
    dp.add_argument("--task-id", default="")
    dp.add_argument("--source", default="hermes_insights")

    mp = sub.add_parser("meter", help="Snapshot, run command, compute delta")
    mp.add_argument("command", nargs=argparse.REMAINDER)
    mp.add_argument("--plan-id", default="")
    mp.add_argument("--task-id", default="")
    mp.add_argument("--source", default="hermes_insights")

    args = parser.parse_args()

    if args.action == "snapshot":
        return snapshot()
    elif args.action == "delta":
        return delta(
            plan_id=getattr(args, "plan_id", ""),
            task_id=getattr(args, "task_id", ""),
            source=getattr(args, "source", "hermes_insights"),
        )
    elif args.action == "meter":
        return meter_command(
            argv=args.command,
            plan_id=getattr(args, "plan_id", ""),
            task_id=getattr(args, "task_id", ""),
            source=getattr(args, "source", "hermes_insights"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
