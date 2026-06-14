#!/usr/bin/env python3
"""Verify coding-agent CLI auth — separate from Hermes profile model reachability.

Used by preflight.sh and pre_dispatch_gate.sh before decomposition.

Exit codes:
  0 — smoke passed (headless execution works)
  1 — binary on PATH but prerequisites or smoke failed
  2 — binary not on PATH (caller may treat as skip/degraded)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugin.coding_agent import (  # noqa: E402
    AUTH_PROBE_TIMEOUT_SECONDS,
    SMOKE_TIMEOUT_SECONDS,
    binary_on_path,
    describe_smoke_failure,
    smoke_test_coding_agent,
)
from plugin.coding_agent_env import (  # noqa: E402
    audit_coding_agent_prerequisites,
    describe_prerequisite_issues,
    ensure_coding_agent_runtime_env,
)
from plugin.coding_agent_auth_cache import write_preflight_cache  # noqa: E402
from plugin.config_overlay import (  # noqa: E402
    resolve_coding_agent,
    resolve_coding_agent_model,
)


def _run(
    cmd: list[str],
    timeout: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test the configured coding-agent CLI (auth gate)."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=AUTH_PROBE_TIMEOUT_SECONDS,
        help=(
            "Smoke timeout seconds (default: auth probe window; "
            f"dashboard uses {SMOKE_TIMEOUT_SECONDS})"
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=f"Use full dashboard smoke timeout ({SMOKE_TIMEOUT_SECONDS}s)",
    )
    parser.add_argument(
        "--prerequisites-only",
        action="store_true",
        help="Check HOME and credential prerequisites without running smoke",
    )
    parser.add_argument(
        "--binary",
        default=None,
        help="Override coding agent binary (default: config / env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override coding agent model (default: config / env)",
    )
    args = parser.parse_args()

    env = ensure_coding_agent_runtime_env(dict(os.environ))
    binary = resolve_coding_agent(REPO_ROOT, coding_agent=args.binary, env=env)
    model = resolve_coding_agent_model(REPO_ROOT, coding_agent_model=args.model, env=env)
    timeout = SMOKE_TIMEOUT_SECONDS if args.full else args.timeout

    if not binary_on_path(binary):
        print(
            f"coding agent binary '{binary}' not on PATH — "
            "install CLI or update coding_agent_binary",
            file=sys.stderr,
        )
        return 2

    prereq_issues = audit_coding_agent_prerequisites(binary, env)
    if prereq_issues:
        print(
            describe_prerequisite_issues(binary, prereq_issues),
            file=sys.stderr,
        )
        if args.prerequisites_only:
            return 1
        # Continue to smoke — execution test is authoritative when files exist
        # but HOME was just repaired in-process.

    if args.prerequisites_only:
        print(f"OK: {binary} prerequisites passed (HOME={env.get('HOME', '?')})")
        return 0

    last_stdout = ""
    last_stderr = ""
    timed_out = False

    def run_capture(cmd: list[str], timeout: int = AUTH_PROBE_TIMEOUT_SECONDS):
        nonlocal last_stdout, last_stderr, timed_out
        try:
            result = _run(cmd, timeout, env)
            last_stdout = result.stdout or ""
            last_stderr = result.stderr or ""
            return result
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            last_stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            last_stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            raise

    fast = not args.full
    try:
        reachable = smoke_test_coding_agent(
            binary, model, run_capture, timeout=timeout, fast=fast
        )
    except subprocess.TimeoutExpired:
        reachable = False

    if reachable is True:
        write_preflight_cache(binary, REPO_ROOT, source="check_coding_agent_cli")
        print(f"OK: {binary} headless smoke passed (model={model}, HOME={env.get('HOME', '?')})")
        return 0

    if prereq_issues and not (last_stdout or last_stderr):
        return 1

    detail = describe_smoke_failure(
        binary,
        stdout=last_stdout,
        stderr=last_stderr,
        timed_out=timed_out,
        run=run_capture,
    )
    if timed_out and not args.full:
        detail += (
            " Override (audit-noted): export PREFLIGHT_SKIP_CODING_AGENT_CLI=1 "
            "and re-run preflight/handoff."
        )
    print(detail, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
