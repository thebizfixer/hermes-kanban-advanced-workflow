#!/usr/bin/env python3
"""Pre-complete gate — block verification-deploy archive without attestation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from card_body import is_verification_deploy, parse_card_body  # noqa: E402
from presentation_acceptance import verification_deploy_attested  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate hermes kanban complete for verify-deploy")
    parser.add_argument("task_id")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    show = subprocess.run(
        ["hermes", "kanban", "show", args.task_id],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if show.returncode != 0:
        print(f"ERROR: cannot show {args.task_id}", file=sys.stderr)
        return 1
    body = show.stdout
    parsed = parse_card_body(body)
    if not is_verification_deploy(parsed, body):
        return 0
    plan_id = parsed.get("plan_id") or ""
    card_key = ""
    for line in body.splitlines():
        if line.strip().startswith("card_key:"):
            card_key = line.split(":", 1)[1].strip()
            break
    if not plan_id or not card_key:
        print("BLOCK: verification-deploy requires plan_id and card_key", file=sys.stderr)
        return 1
    if not verification_deploy_attested(Path(args.repo_root).resolve(), plan_id, card_key):
        print(
            "BLOCK: verification_deploy_requires_attestation — "
            f"write .hermes/kanban/card-attestations/{plan_id}-{card_key}.json",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
