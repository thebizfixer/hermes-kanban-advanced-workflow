#!/usr/bin/env python3
"""
cycle_detector.py — Yellow Belt thrash detection (≥3 same E-code + HEAD).

Notify at threshold; block dispatch on balanced/strict when CYCLE_DETECTED.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from governance_profile import (  # noqa: E402
    emit_strict_notification,
    resolve_governance_profile,
    should_notify_operator,
)

_THRESHOLD = 3
_ECODE_RE = re.compile(r"\b(E\d{3}_[A-Z0-9_]+|P\d{3}_[A-Z0-9_]+|verification_deploy_requires_attestation)\b")


@dataclass
class CycleHit:
    ecode: str
    head: str
    count: int
    task_ids: list[str]


def _hermes_list() -> str:
    result = subprocess.run(
        ["hermes", "kanban", "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return result.stdout if result.returncode == 0 else ""


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    return result.stdout.strip()[:12] if result.returncode == 0 else "unknown"


def _card_failure_codes(body: str) -> list[str]:
    codes = _ECODE_RE.findall(body)
    block_reason = ""
    for line in body.splitlines():
        if "block reason" in line.lower() or line.strip().startswith("blocked:"):
            block_reason = line
    codes.extend(_ECODE_RE.findall(block_reason))
    return list(dict.fromkeys(codes))


def detect_cycles(repo_root: Path, plan_id: str = "") -> list[CycleHit]:
    head = _git_head(repo_root)
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)

    for line in _hermes_list().splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("t_"):
            continue
        tid = parts[0]
        show = subprocess.run(
            ["hermes", "kanban", "show", tid],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if show.returncode != 0:
            continue
        body = show.stdout
        if plan_id and f"plan_id: {plan_id}" not in body and f"plan_id:{plan_id}" not in body.replace(" ", ""):
            continue
        if "blocked" not in body.lower() and "failure" not in body.lower():
            continue
        for code in _card_failure_codes(body):
            buckets[(code, head)].append(tid)

    hits: list[CycleHit] = []
    for (code, h), tids in buckets.items():
        if len(tids) >= _THRESHOLD:
            hits.append(CycleHit(ecode=code, head=h, count=len(tids), task_ids=tids))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect repeated failure cycles on board")
    parser.add_argument("--plan-id", default="")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--profile", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile = resolve_governance_profile(cli_override=args.profile or None)
    hits = detect_cycles(repo_root, plan_id=args.plan_id)

    if args.json:
        print(json.dumps([h.__dict__ for h in hits], indent=2))
    else:
        for h in hits:
            print(
                f"CYCLE_DETECTED: {h.ecode} x{h.count} at HEAD {h.head} "
                f"tasks={','.join(h.task_ids[:5])}"
            )

    if not hits:
        return 0

    if should_notify_operator(profile):
        for h in hits:
            emit_strict_notification(
                task_id=h.task_ids[0] if h.task_ids else "",
                reason=f"CYCLE_DETECTED {h.ecode} x{h.count} at HEAD {h.head}",
                failure_class="cycle_detect",
            )

    if profile == "advisory":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
