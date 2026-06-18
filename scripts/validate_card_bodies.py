#!/usr/bin/env python3
"""
validate_card_bodies.py — Plan fidelity gate for decomposed card bodies.

WARN at decompose --dry-run (advisory / --dry-run exit 0).
BLOCK at pre_dispatch_gate (balanced/strict exit 1).

Usage:
  python3 validate_card_bodies.py --plan .hermes/kanban/plans/foo.plan.md
  python3 validate_card_bodies.py --plan-id foo --repo-root .
  python3 validate_card_bodies.py --plan-id foo --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_body_fidelity import (  # noqa: E402
    FidelityViolation,
    _fmt_violation,
    validate_parsed_cards,
    validate_plan_file,
)
from decompose_stamp import stamp_all_impl_cards  # noqa: E402
from governance_profile import resolve_governance_profile  # noqa: E402
from plan_parse import load_plan_text, parse_plan  # noqa: E402
from plan_paths import resolve_plan_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate card bodies against plan fidelity")
    parser.add_argument("--plan", help="Path to plan markdown")
    parser.add_argument("--plan-id", help="Plan id (resolves via plan_search_dirs)")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--dry-run", action="store_true", help="WARN only; exit 0 unless --strict-exit")
    parser.add_argument("--strict-exit", action="store_true", help="Exit 1 on violations even with --dry-run")
    parser.add_argument("--profile", default="", help="advisory | balanced | strict")
    parser.add_argument("--json", action="store_true", help="Emit JSON violations")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile = resolve_governance_profile(cli_override=args.profile or None)
    if args.dry_run and not args.profile:
        profile = "advisory"

    plan_path: Path | None = None
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.is_file():
            print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
            return 1
    elif args.plan_id:
        resolved = resolve_plan_file(str(repo_root), args.plan_id, "")
        if not resolved:
            print(f"ERROR: cannot resolve plan for plan_id={args.plan_id}", file=sys.stderr)
            return 1
        plan_path = Path(resolved)
        if not plan_path.is_file():
            plan_path = repo_root / resolved
    else:
        print("ERROR: pass --plan or --plan-id", file=sys.stderr)
        return 1

    if not plan_path.is_file():
        print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
        return 1

    # Stamp parity with decompose
    parsed = parse_plan(str(plan_path))
    all_cards = parsed.get("cards") or []
    plan_file_rel = ""
    try:
        plan_file_rel = plan_path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        plan_file_rel = str(plan_path)
    stamp_all_impl_cards(
        all_cards,
        plan_id=parsed.get("plan_id", ""),
        plan_file_rel=plan_file_rel,
        plan_path=str(plan_path),
    )
    plan_text = load_plan_text(plan_path)
    violations = validate_parsed_cards(
        plan_path=plan_path,
        plan_text=plan_text,
        cards=all_cards,
        repo_root=repo_root,
        plan_id=parsed.get("plan_id", ""),
        profile=profile,
    )

    blocking = [v for v in violations if v.severity == "block"]
    warns = [v for v in violations if v.severity == "warn"]

    if args.json:
        payload = [
            {
                "code": v.code,
                "severity": v.severity,
                "message": v.message,
                "card_key": v.card_key,
                "plan_lineno": v.plan_lineno,
                "plan_file": v.plan_file,
            }
            for v in violations
        ]
        print(json.dumps(payload, indent=2))
    else:
        for v in violations:
            print(_fmt_violation(v), file=sys.stderr)

    if blocking:
        print(
            f"[validate_card_bodies] {len(blocking)} blocking, {len(warns)} warnings",
            file=sys.stderr,
        )
        if args.dry_run and not args.strict_exit:
            return 0
        return 1
    if warns:
        print(f"[validate_card_bodies] {len(warns)} warning(s)", file=sys.stderr)
    else:
        print("[validate_card_bodies] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
