#!/usr/bin/env python3
"""Portable parsers for Hermes kanban CLI / git worktree / process output."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TASK_ID_RE = re.compile(r"t_\w+")
_PARENTS_LINE_RE = re.compile(r"parents:\s*(.+)", re.IGNORECASE)
_MAX_RETRIES_LINE_RE = re.compile(r"max-retries:\s*(\d+)", re.IGNORECASE)
_CREATED_LINE_RE = re.compile(r"created.*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", re.IGNORECASE)
_WORKTREE_BRANCH_RE = re.compile(r"\[([^\]]+)\]")
_COMMIT_HASH_RE = re.compile(r"Commit ([0-9a-f]{7,40})", re.IGNORECASE)
_PYTEST_CMD_RE = re.compile(r"pytest[^`\"]+")


def extract_task_ids(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _TASK_ID_RE.finditer(text):
        tid = m.group(0)
        if tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def extract_first_integer(text: str) -> int | None:
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def extract_parent_task_ids(show_text: str) -> list[str]:
    for line in show_text.splitlines():
        m = _PARENTS_LINE_RE.search(line)
        if m:
            return extract_task_ids(m.group(1))
    return []


def extract_max_retries(show_text: str) -> int | None:
    for line in show_text.splitlines():
        m = _MAX_RETRIES_LINE_RE.search(line)
        if m:
            return int(m.group(1))
    return None


def extract_created_timestamp(show_text: str) -> str | None:
    for line in show_text.splitlines():
        m = _CREATED_LINE_RE.search(line)
        if m:
            return m.group(1)
    return None


def extract_worktree_branch(worktree_line: str) -> str:
    m = _WORKTREE_BRANCH_RE.search(worktree_line)
    if not m:
        return "detached"
    branch = m.group(1).strip()
    return branch if branch else "detached"


def extract_commit_hash_from_body(body: str) -> str | None:
    m = _COMMIT_HASH_RE.search(body)
    return m.group(1) if m else None


def extract_pytest_commands(plan_text: str, limit: int = 5) -> list[str]:
    cmds = [m.group(0).strip() for m in _PYTEST_CMD_RE.finditer(plan_text)]
    return cmds[:limit]


def _read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _emit(result, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(result))
    elif isinstance(result, list):
        print("\n".join(str(x) for x in result))
    else:
        print(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI output parsing utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_io(p: argparse.ArgumentParser) -> None:
        p.add_argument("--text", default=None)
        p.add_argument("--file", default=None)
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("task-ids")
    add_io(p)
    p.set_defaults(func=lambda a: extract_task_ids(_read_text(a)))

    p = sub.add_parser("parents")
    add_io(p)
    p.set_defaults(func=lambda a: extract_parent_task_ids(_read_text(a)))

    p = sub.add_parser("max-retries")
    add_io(p)
    p.set_defaults(func=lambda a: extract_max_retries(_read_text(a)) or 0)

    p = sub.add_parser("created")
    add_io(p)
    p.set_defaults(func=lambda a: extract_created_timestamp(_read_text(a)) or "")

    p = sub.add_parser("worktree-branch")
    add_io(p)
    p.set_defaults(func=lambda a: extract_worktree_branch(_read_text(a)))

    p = sub.add_parser("commit-hash")
    add_io(p)
    p.set_defaults(func=lambda a: extract_commit_hash_from_body(_read_text(a)) or "")

    p = sub.add_parser("pytest-cmds")
    add_io(p)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=lambda a: extract_pytest_commands(_read_text(a), limit=a.limit))

    args = parser.parse_args(argv)
    result = args.func(args)
    _emit(result, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
