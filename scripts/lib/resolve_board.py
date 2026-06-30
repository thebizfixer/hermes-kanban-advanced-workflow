#!/usr/bin/env python3
"""CLI wrapper for board_resolver.resolve_board_for_plan().

Usage:
    python3 scripts/lib/resolve_board.py --plan-id <plan_id>
    python3 scripts/lib/resolve_board.py --plan-id <plan_id> --hermes-home /path

Prints resolved board slug to stdout. Exit codes: 0=found, 1=not found, 2=error.
"""

import argparse
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from lib.board_resolver import resolve_board_for_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a kanban board slug for a plan_id"
    )
    parser.add_argument("--plan-id", required=True, help="Plan identifier")
    parser.add_argument("--project-root", type=Path, default=None, help="Project root path")
    parser.add_argument("--hermes-home", type=Path, default=None, help="Hermes home directory")
    args = parser.parse_args()

    plan_id = args.plan_id.strip()
    if not plan_id:
        print("error: --plan-id is required", file=sys.stderr)
        return 2

    slug = resolve_board_for_plan(
        plan_id,
        project_root=args.project_root,
        hermes_home=args.hermes_home,
    )

    if slug:
        print(slug)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
