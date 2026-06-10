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
    plan_entries = [e for e in entries if e.get("plan_id") == plan_id]
    if not plan_entries:
        print(f"No token data found for plan '{plan_id}'")
        return

    total_tasks = len(plan_entries)
    total_cursor = sum((e.get("cursor", {}) or {}).get("total", 0) for e in plan_entries)
    total_cursor_cache = sum((e.get("cursor", {}) or {}).get("cache_read_tokens", 0) for e in plan_entries)

    print(f"Token Usage Report — Plan: {plan_id}")
    print(f"{'='*60}")
    print(f"Tasks: {total_tasks}")
    print()
    print(f"{'Source':<30} {'Tokens':>12} {'Cache':>10}")
    print("-" * 52)
    print(f"{'Cursor agent':<30} {format_tokens(total_cursor):>12} {format_tokens(total_cursor_cache):>10}")
    print("-" * 52)
    print(f"{'TOTAL':<30} {format_tokens(total_cursor):>12}")
    print()

    if plan_entries:
        print("Per-task breakdown:")
        print(f"{'Task ID':<20} {'Model':<20} {'Tokens':>10} {'Status':>10}")
        print("-" * 60)
        for e in sorted(plan_entries, key=lambda x: x.get("task_id", "")):
            tid = e.get("task_id", "unknown")
            model = e.get("cursor", {}).get("model", "unknown")
            tokens = e.get("cursor", {}).get("total", 0)
            status = e.get("status", "unknown")
            print(f"{tid:<20} {model:<20} {format_tokens(tokens):>10} {status:>10}")


def report_task(task_id: str, entries: list[dict]):
    matches = [e for e in entries if e.get("task_id") == task_id]
    if not matches:
        print(f"No token data found for task '{task_id}'")
        return
    for e in matches:
        c = e.get("cursor", {}) or {}
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
