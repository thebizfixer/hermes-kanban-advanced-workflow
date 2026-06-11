#!/usr/bin/env python3
"""Verify coding-agent CLI auth — separate from Hermes profile model reachability.

Used by preflight.sh and pre_dispatch_gate.sh before decomposition.

Exit codes:
  0 — smoke passed (headless execution works)
  1 — binary on PATH but smoke failed (auth, trust, timeout, model)
  2 — binary not on PATH (caller may treat as skip/degraded)
"""

from __future__ import annotations

import argparse
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
from plugin.config_overlay import (  # noqa: E402
    resolve_coding_agent,
    resolve_coding_agent_model,
)


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
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

    env = dict(**{k: v for k, v in __import__("os").environ.items()})
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

    last_stdout = ""
    last_stderr = ""
    timed_out = False

    def run_capture(cmd: list[str], timeout: int = 90):
        nonlocal last_stdout, last_stderr, timed_out
        try:
            result = _run(cmd, timeout)
            last_stdout = result.stdout or ""
            last_stderr = result.stderr or ""
            return result
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            last_stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            last_stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            raise

    try:
        reachable = smoke_test_coding_agent(binary, model, run_capture, timeout=timeout)
    except subprocess.TimeoutExpired:
        reachable = False

    if reachable is True:
        print(f"OK: {binary} headless smoke passed (model={model})")
        return 0

    detail = describe_smoke_failure(
        binary,
        stdout=last_stdout,
        stderr=last_stderr,
        timed_out=timed_out,
        run=run_capture,
    )
    print(detail, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
