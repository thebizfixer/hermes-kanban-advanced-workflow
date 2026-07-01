"""Hermes config.yaml keys applied during kanban-advanced init / dashboard bootstrap."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

DISPATCH_STALE_TIMEOUT_SECONDS = "14400"
FAILURE_LIMIT = "5"
BLOCK_RECURRENCE_LIMIT_TARGET = 5  # Must match BLOCK_RECURRENCE_LIMIT in hermes_cli/kanban_db.py


def patch_block_recurrence_limit(
    log: Callable[[str], None] | None = None,
) -> bool:
    """Patch hermes_cli/kanban_db.py BLOCK_RECURRENCE_LIMIT to 5 (idempotent).

    Returns True if the limit is already at the target or was patched successfully.
    """
    import os

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    target = os.path.join(
        hermes_home, "hermes-agent", "hermes_cli", "kanban_db.py"
    )
    if not os.path.isfile(target):
        _log(
            f"   !  Could not find kanban_db.py at {target} — "
            "patch BLOCK_RECURRENCE_LIMIT manually"
        )
        return False

    try:
        with open(target, "r", encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        _log(f"   !  Could not read {target}: {exc}")
        return False

    if "BLOCK_RECURRENCE_LIMIT = 5" in original:
        _log("   OK BLOCK_RECURRENCE_LIMIT = 5")
        return True

    patched = original.replace(
        "BLOCK_RECURRENCE_LIMIT = 2", f"BLOCK_RECURRENCE_LIMIT = {BLOCK_RECURRENCE_LIMIT_TARGET}"
    )
    if patched == original:
        _log(
            "   !  Could not locate BLOCK_RECURRENCE_LIMIT assignment in "
            f"{target} — patch manually"
        )
        return False

    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(patched)
    except OSError as exc:
        _log(f"   !  Could not write {target}: {exc}")
        return False

    _log(f"   OK BLOCK_RECURRENCE_LIMIT = {BLOCK_RECURRENCE_LIMIT_TARGET} (patched)")
    return True


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
