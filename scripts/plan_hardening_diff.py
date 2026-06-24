#!/usr/bin/env python3
"""
plan_hardening_diff.py — Report-only drift between plan Spec/Contracts and workspace.

Never auto-edits plan markdown. Operator approves remediation spawn.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lib.card_body import normalize_file_path  # noqa: E402
from plan_parse import (  # noqa: E402
    extract_optimization_section,
    find_backtick_file_refs,
    load_plan_text,
    split_card_blocks,
)

_VERIFY_RG_RE = re.compile(
    r"Verify:\s*rg\s+(?:-n\s+)?['\"]?([^'\"]+)['\"]?\s+(\S+)",
    re.IGNORECASE,
)
_CONTRACT_RE = re.compile(r"^Contracts:\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass
class DriftItem:
    kind: str
    path: str
    detail: str
    plan_lineno: int | None = None


def _rg_has_pattern(pattern: str, path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        result = subprocess.run(
            ["rg", "-q", pattern, str(path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        text = path.read_text(encoding="utf-8", errors="replace")
        return bool(re.search(pattern, text))


def collect_verify_lines(plan_text: str) -> list[tuple[str, str, int]]:
    """Return (pattern, path, lineno) from Verify: rg bullets."""
    items: list[tuple[str, str, int]] = []
    for i, line in enumerate(plan_text.splitlines(), 1):
        m = _VERIFY_RG_RE.search(line)
        if m:
            items.append((m.group(1), normalize_file_path(m.group(2)), i))
    return items


def collect_contract_files(plan_text: str) -> list[tuple[str, int]]:
    opt = extract_optimization_section(plan_text)
    blob = opt or plan_text
    out: list[tuple[str, int]] = []
    base = plan_text.find(blob) if blob in plan_text else 0
    base_line = plan_text[:base].count("\n") + 1 if base else 1
    for i, line in enumerate(blob.splitlines()):
        for ref in find_backtick_file_refs(line):
            p = normalize_file_path(ref)
            if p.endswith((".py", ".ts", ".tsx", ".js", ".sh")):
                out.append((p, base_line + i))
    return out


def run_diff(plan_path: Path, repo_root: Path) -> list[DriftItem]:
    plan_text = load_plan_text(plan_path)
    drift: list[DriftItem] = []

    for pattern, path, lineno in collect_verify_lines(plan_text):
        full = repo_root / path
        if not full.is_file():
            drift.append(
                DriftItem(
                    kind="verify_path_missing",
                    path=path,
                    detail=f"Verify: rg target missing: {path}",
                    plan_lineno=lineno,
                )
            )
            continue
        if not _rg_has_pattern(pattern, full):
            drift.append(
                DriftItem(
                    kind="verify_pattern_miss",
                    path=path,
                    detail=f"Verify: rg pattern not found: {pattern!r} in {path}",
                    plan_lineno=lineno,
                )
            )

    if _CONTRACT_RE.search(plan_text):
        for path, lineno in collect_contract_files(plan_text):
            if not (repo_root / path).is_file():
                drift.append(
                    DriftItem(
                        kind="contract_file_missing",
                        path=path,
                        detail=f"Contracts reference missing file: {path}",
                        plan_lineno=lineno,
                    )
                )

    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description="Report plan vs workspace drift (read-only)")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    repo_root = Path(args.repo_root).resolve()
    drift = run_diff(plan_path, repo_root)

    if args.json:
        print(json.dumps([d.__dict__ for d in drift], indent=2))
    else:
        for d in drift:
            loc = f"{plan_path}:{d.plan_lineno}: " if d.plan_lineno else ""
            print(f"DRIFT: {loc}{d.kind} {d.path} — {d.detail}")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
