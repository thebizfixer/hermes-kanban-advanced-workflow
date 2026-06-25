#!/usr/bin/env python3
"""
Kanban token usage reporter.

Aggregates token usage across kanban plan executions from JSONL token log.
Reads from $KANBAN_TOKEN_LOG or default ~/.hermes/kanban/tokens.jsonl.

Usage:
    python scripts/kanban_token_report.py --plan my-plan
    python scripts/kanban_token_report.py --task t_abc123
    python scripts/kanban_token_report.py --all
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

# Neutral config-driven reporting (respects coding_agent_binary in kanban-config)
def _get_coding_agent_binary():
    for base in (Path.cwd(), Path.home()):
        cfg = base / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
        if cfg.exists():
            try:
                with open(cfg, encoding="utf-8") as f:
                    for line in f:
                        if "coding_agent_binary:" in line:
                            val = line.split(":", 1)[1].strip().strip("\"'")
                            if val:
                                return val
            except Exception:
                pass
    return os.environ.get("KANBAN_CODING_AGENT") or os.environ.get("KANBAN_CODING_AGENT_BINARY") or "hermes"

def _get_agent_label():
    b = _get_coding_agent_binary().lower()
    if "hermes" in b:
        return "hermes agent"
    if "cursor" in b:
        return "cursor agent"
    return f"{_get_coding_agent_binary()} agent"


def _token_log_path() -> Path:
    env = os.environ.get("KANBAN_TOKEN_LOG", "")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "kanban" / "tokens.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def report_plan(plan_id: str, entries: list[dict]):
    # Scope to most recent run only (same logic as generate_postmortem.py)
    plan_entries = [e for e in entries if e.get("plan_id") == plan_id]
    # Find the most recent planning-complete or decompose-complete checkpoint
    planning_ts = None
    decompose_ts = None
    for e in plan_entries:
        status = str(e.get("status") or e.get("extra", {}).get("checkpoint", "")).strip()
        ts = str(e.get("timestamp") or "")
        if not ts:
            continue
        if status == "planning-complete":
            if planning_ts is None or ts > planning_ts:
                planning_ts = ts
        elif status == "decompose-complete":
            if decompose_ts is None or ts > decompose_ts:
                decompose_ts = ts
    boundary_ts = planning_ts or decompose_ts
    if boundary_ts:
        plan_entries = [e for e in plan_entries if str(e.get("timestamp") or "") >= boundary_ts]

    if not plan_entries:
        print(f"No token data found for plan '{plan_id}'")
        return

    total_tasks = len(plan_entries)

    # Neutral: use config + prefer "agent" section
    binary = _get_coding_agent_binary()
    label = _get_agent_label()

    def _agent_total(e):
        ag = e.get("agent") or {}
        if ag.get("total") is not None:
            return int(ag.get("total", 0))
        sec = "hermes" if "hermes" in binary.lower() else "cursor"
        s = e.get(sec, {}) or {}
        return int(s.get("total", 0) or 0)

    def _agent_model(e):
        ag = e.get("agent") or {}
        if ag.get("model"):
            return ag["model"]
        sec = "hermes" if "hermes" in binary.lower() else "cursor"
        return (e.get(sec, {}) or {}).get("model", "unknown")

    total = sum(_agent_total(e) for e in plan_entries)
    total_cache = sum(((e.get("agent", {}) or {}).get("cache_read_tokens", 0) or 0) for e in plan_entries)

    print(f"Token Usage Report — Plan: {plan_id}")
    print(f"{'='*60}")
    print(f"Tasks: {total_tasks}")
    print()
    print(f"{'Source':<30} {'Tokens':>12} {'Cache':>10}")
    print("-" * 52)
    print(f"{label:<30} {format_tokens(total):>12} {format_tokens(total_cache):>10}")
    print("-" * 52)
    print(f"{'TOTAL':<30} {format_tokens(total):>12}")
    print()

    if plan_entries:
        print("Per-task breakdown:")
        print(f"{'Task ID':<20} {'Model':<20} {'Tokens':>10} {'Status':>10}")
        print("-" * 60)
        for e in sorted(plan_entries, key=lambda x: x.get("task_id", "")):
            tid = e.get("task_id", "unknown")
            model = _agent_model(e)
            tokens = _agent_total(e)
            status = e.get("status", "unknown")
            print(f"{tid:<20} {model:<20} {format_tokens(tokens):>10} {status:>10}")


def report_task(task_id: str, entries: list[dict]):
    matches = [e for e in entries if e.get("task_id") == task_id]
    if not matches:
        print(f"No token data found for task '{task_id}'")
        return
    binary = _get_coding_agent_binary()
    sec = "hermes" if "hermes" in binary.lower() else "cursor"
    for e in matches:
        c = e.get("agent") or e.get(sec, {}) or {}
        print(f"Task: {task_id}")
        print(f"  Plan:      {e.get('plan_id', 'unknown')}")
        print(f"  Model:     {c.get('model', 'unknown')}")
        print(f"  Input:     {format_tokens(c.get('input_tokens', 0))}")
        print(f"  Output:    {format_tokens(c.get('output_tokens', 0))}")
        print(f"  Cache:     {format_tokens(c.get('cache_read_tokens', 0))}")
        print(f"  Total:     {format_tokens(c.get('total', 0))}")
        print(f"  Duration:  {e.get('duration_seconds', 0):.1f}s")
        print(f"  Status:    {e.get('status', 'unknown')}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Kanban token usage reporter")
    parser.add_argument("--plan", help="Plan ID to report on")
    parser.add_argument("--task", help="Kanban task ID to report on")
    parser.add_argument("--all", action="store_true", help="Report all plans")
    parser.add_argument("--csv", action="store_true", help="Export as CSV")
    args = parser.parse_args()

    entries = read_jsonl(_token_log_path())

    if args.plan:
        report_plan(args.plan, entries)
    elif args.task:
        report_task(args.task, entries)
    elif args.all or True:
        plans = defaultdict(list)
        for e in entries:
            plans[e.get("plan_id", "unknown")].append(e)
        if not plans:
            print("No token data found.")
            print(f"Expected log at: {_token_log_path()}")
            return
        for plan_id in sorted(plans):
            report_plan(plan_id, plans[plan_id])
            print()


if __name__ == "__main__":
    main()
