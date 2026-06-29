"""Hermes config.yaml keys applied during kanban-advanced init / dashboard bootstrap."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

DISPATCH_STALE_TIMEOUT_SECONDS = "14400"
FAILURE_LIMIT = "5"


def apply_hermes_kanban_bootstrap_config(
    run: Callable[..., subprocess.CompletedProcess],
    hermes_bin: str = "hermes",
    log: Callable[[str], None] | None = None,
) -> None:
    """Set kanban-advanced required Hermes config keys (idempotent)."""
    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    r_ad = run([hermes_bin, "config", "set", "kanban.auto_decompose", "false"])
    if r_ad.returncode == 0:
        _log("   OK kanban.auto_decompose = false")
    else:
        _log(
            "   !  Could not set kanban.auto_decompose — set manually: "
            "hermes config set kanban.auto_decompose false"
        )

    r_stale = run(
        [
            hermes_bin,
            "config",
            "set",
            "kanban.dispatch_stale_timeout_seconds",
            DISPATCH_STALE_TIMEOUT_SECONDS,
        ]
    )
    if r_stale.returncode == 0:
        _log(
            f"   OK kanban.dispatch_stale_timeout_seconds = {DISPATCH_STALE_TIMEOUT_SECONDS}"
        )
    else:
        _log(
            "   !  Could not set kanban.dispatch_stale_timeout_seconds — set manually: "
            f"hermes config set kanban.dispatch_stale_timeout_seconds {DISPATCH_STALE_TIMEOUT_SECONDS}"
        )

    r_fl = run(
        [
            hermes_bin,
            "config",
            "set",
            "kanban.failure_limit",
            FAILURE_LIMIT,
        ]
    )
    if r_fl.returncode == 0:
        _log(f"   OK kanban.failure_limit = {FAILURE_LIMIT}")
    else:
        _log(
            "   !  Could not set kanban.failure_limit — set manually: "
            f"hermes config set kanban.failure_limit {FAILURE_LIMIT}"
        )
