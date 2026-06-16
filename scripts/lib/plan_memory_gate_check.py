#!/usr/bin/env python3
"""Validate plan memory freshness vs on-disk plan (pre-dispatch gate). Exit 0 pass, 1 fail."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _impl_card_count(plan_path: Path, bundle_scripts: Path) -> int:
    sys.path.insert(0, str(bundle_scripts))
    import kanban_decompose as kd  # noqa: WPS433

    parsed = kd.parse_plan(str(plan_path))
    return len([c for c in parsed["cards"] if c["type"] not in ("gate", "root", "audit")])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan memory gate check")
    parser.add_argument("--memory", required=True, help="Path to plan memory JSON")
    parser.add_argument("--plan", default="", help="Relative or absolute plan file path")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument("--bundle-scripts", required=True, help="Path to scripts/ bundle")
    args = parser.parse_args(argv)

    mem_path = Path(args.memory)
    if not mem_path.is_file():
        print(f"plan memory missing: {mem_path}", file=sys.stderr)
        return 1

    data = json.loads(mem_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("plan memory is not a JSON object", file=sys.stderr)
        return 1

    repo_root = Path(args.repo_root)
    plan_path = Path(args.plan) if args.plan else None
    if plan_path and not plan_path.is_absolute():
        plan_path = repo_root / plan_path
    if not plan_path or not plan_path.is_file():
        plan_rel = data.get("plan_path") or ""
        if plan_rel:
            plan_path = Path(plan_rel)
            if not plan_path.is_absolute():
                plan_path = repo_root / plan_path

    if plan_path and plan_path.is_file():
        content = plan_path.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        stored_sha = data.get("plan_sha256")
        if stored_sha and stored_sha != sha:
            print(f"plan_sha256 mismatch: memory={stored_sha[:12]}… disk={sha[:12]}…", file=sys.stderr)
            return 1

        bundle_scripts = Path(args.bundle_scripts)
        parsed_count = _impl_card_count(plan_path, bundle_scripts)
        mem_count = data.get("card_count")
        if mem_count is not None and int(mem_count) != parsed_count:
            print(
                f"card_count mismatch: memory={mem_count} parsed={parsed_count}",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
