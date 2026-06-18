#!/usr/bin/env python3
"""Anchor shape audit — declared pins vs prose-only line refs (sanity / optimize gate)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.plan_parse import audit_anchors, load_plan_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit plan Anchor: pins and Files: shape")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when non-trivial cards lack Anchor:")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"ERROR: Plan file not found: {plan_path}", file=sys.stderr)
        return 2

    report = audit_anchors(load_plan_text(plan_path))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Anchor audit: {plan_path} ===")
        print(f"Declared anchors: {report['declared_anchor_count']}")
        missing = report["cards_missing_anchor"]
        if missing:
            print(f"FAIL: {len(missing)} non-trivial code-gen card(s) missing Anchor: - {', '.join(missing)}")
        else:
            print("OK: Non-trivial code-gen cards include Anchor:")
        plain = report["files_not_plain_path"]
        if plain:
            print(f"WARN: {len(plain)} Files: line(s) use markdown links - use plain repo-relative paths")
        prose = report["prose_line_refs"]
        if prose:
            print(f"INFO: {len(prose)} prose L-ref(s) not auto-verified (sanity-check scope)")

    if args.strict and report["cards_missing_anchor"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
