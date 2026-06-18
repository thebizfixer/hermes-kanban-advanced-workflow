#!/usr/bin/env python3
"""Write and verify verification-deploy card attestation JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from presentation_acceptance import (  # noqa: E402
    card_attestation_path,
    verification_deploy_attested,
)


def _validate_schema(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ("plan_id", "card_key", "attested_at", "operator", "evidence"):
        if not data.get(key):
            errors.append(f"missing required field: {key}")
    return errors


def cmd_write(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    payload = {
        "plan_id": args.plan_id,
        "card_key": args.card_key,
        "attested_at": datetime.now(timezone.utc).isoformat(),
        "operator": args.operator,
        "evidence": args.evidence,
    }
    if args.visual_regression:
        payload["visual_regression"] = args.visual_regression
    errs = _validate_schema(payload)
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    path = card_attestation_path(repo, args.plan_id, args.card_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    ok = verification_deploy_attested(repo, args.plan_id, args.card_key)
    if ok:
        print("PASS")
        return 0
    print("FAIL: attestation missing or invalid", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verification-deploy card attestation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="Write attestation JSON")
    w.add_argument("--plan-id", required=True)
    w.add_argument("--card-key", required=True)
    w.add_argument("--operator", required=True)
    w.add_argument("--evidence", required=True)
    w.add_argument("--visual-regression", default="")
    w.add_argument("--repo-root", default=".")
    w.set_defaults(func=cmd_write)

    v = sub.add_parser("verify", help="Verify attestation exists")
    v.add_argument("--plan-id", required=True)
    v.add_argument("--card-key", required=True)
    v.add_argument("--repo-root", default=".")
    v.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
