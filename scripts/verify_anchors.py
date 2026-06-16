#!/usr/bin/env python3
"""Pre-hardening anchor verification gate (platform-neutral)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.governance_profile import (  # noqa: E402
    failures_are_blocking,
    resolve_governance_profile,
    warnings_are_blocking,
)
from lib.plan_parse import AnchorRef, extract_anchors, load_plan_text  # noqa: E402

STALE_THRESHOLD = 5


def _repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(".").resolve()


def _resolve_file(repo_root: Path, file_path: str) -> Path | None:
    candidate = repo_root / file_path
    if candidate.is_file():
        return candidate
    direct = Path(file_path)
    if direct.is_file():
        return direct
    return None


def _verify_anchor(
    repo_root: Path,
    anchor: AnchorRef,
    *,
    stale_threshold: int = STALE_THRESHOLD,
) -> tuple[str, str]:
    """Return (status, message) where status is pass|warn|fail."""
    print(f"Anchor: {anchor.file} L{anchor.line}")

    resolved = _resolve_file(repo_root, anchor.file)
    if resolved is None:
        return "fail", f"File not found: {anchor.file}"

    lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    if anchor.line < 1 or anchor.line > len(lines):
        return "fail", f"Line {anchor.line} does not exist in {anchor.file}"

    symbol = anchor.symbol_hint
    if not symbol:
        return "pass", f"Line L{anchor.line} exists in {anchor.file} (no function name to cross-reference)"

    context_start = max(1, anchor.line - stale_threshold)
    context_end = min(len(lines), anchor.line + stale_threshold)
    window = lines[context_start - 1 : context_end]
    pattern = re.compile(rf"^\s*(?:def|class|async def)\s+{re.escape(symbol)}\b")
    found_at = None
    for i, line in enumerate(window):
        if pattern.search(line):
            found_at = context_start + i
            break

    if found_at is None:
        return (
            "fail",
            f"'{symbol}' not found ±{stale_threshold} lines of L{anchor.line} in {anchor.file}",
        )

    offset = found_at - anchor.line
    offset_abs = abs(offset)
    if offset_abs == 0:
        return "pass", f"'{symbol}' at L{found_at} (exact match)"
    if offset_abs <= stale_threshold:
        return "warn", f"'{symbol}' at L{found_at} (offset {offset}) — anchor is L{anchor.line}"
    return "fail", f"'{symbol}' at L{found_at} (offset {offset}) exceeds threshold"


def run_verification(
    plan_path: Path,
    *,
    profile: str,
    json_out: bool = False,
) -> int:
    repo_root = _repo_root()
    plan_text = load_plan_text(plan_path)
    anchors = extract_anchors(plan_text)

    failures = 0
    warnings = 0
    checked = 0
    results: list[dict] = []

    if not json_out:
        print(f"=== Anchor Verification: {plan_path} ===")
        print("")
        print(f"Governance profile: {profile}")

    for anchor in anchors:
        status, msg = _verify_anchor(repo_root, anchor)
        checked += 1
        results.append(
            {
                "file": anchor.file,
                "line": anchor.line,
                "symbol": anchor.symbol_hint,
                "status": status,
                "message": msg,
            }
        )
        if not json_out:
            if status == "pass":
                print(f"  \033[32m✓ {msg}\033[0m")
            elif status == "warn":
                print(f"  \033[33m⚠ WARN: {msg}\033[0m")
                warnings += 1
            else:
                print(f"  \033[31m✗ FAIL: {msg}\033[0m")
                failures += 1

    if json_out:
        print(
            json.dumps(
                {
                    "plan": str(plan_path),
                    "profile": profile,
                    "anchors_found": len(anchors),
                    "anchors_checked": checked,
                    "failures": failures,
                    "warnings": warnings,
                    "results": results,
                }
            )
        )
        exit_code = 0
        if failures > 0 and failures_are_blocking(profile):
            exit_code = 1
        elif warnings > 0 and warnings_are_blocking(profile):
            exit_code = 1
        return exit_code

    print("")
    print(
        f"=== Results: {len(anchors)} anchors found, {checked} verified, "
        f"{failures} failures, {warnings} warnings ==="
    )

    exit_code = 0
    if failures > 0:
        if failures_are_blocking(profile):
            print(f"\033[31mBLOCKED: {failures} anchor(s) could not be verified against HEAD.\033[0m")
            exit_code = 1
        else:
            print(
                f"\033[33mPASS (advisory): {failures} anchor failure(s) downgraded "
                "— review before hardening.\033[0m"
            )
    if warnings > 0:
        if warnings_are_blocking(profile):
            print(f"\033[33mBLOCKED (strict profile): {warnings} warning(s) treated as failures.\033[0m")
            exit_code = 1
        else:
            print(
                f"\033[33mPASS with {warnings} stale anchor warning(s). "
                "Re-verify line numbers before hardening.\033[0m"
            )
    if failures == 0 and warnings == 0:
        print(f"\033[32mPASS: All {len(anchors)} anchors verified against HEAD.\033[0m")

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify plan anchors against HEAD")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--profile", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"ERROR: Plan file not found: {plan_path}", file=sys.stderr)
        return 2

    profile_override = "strict" if args.strict else (args.profile or None)
    profile = resolve_governance_profile(cli_override=profile_override, repo_root=_repo_root())
    if profile == "strict":
        pass  # warnings_are_blocking handles strict

    return run_verification(plan_path, profile=profile, json_out=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
