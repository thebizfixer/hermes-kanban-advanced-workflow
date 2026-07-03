"""Hermes config.yaml keys applied during kanban-advanced init / dashboard bootstrap."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

import yaml

DISPATCH_STALE_TIMEOUT_SECONDS = "14400"
FAILURE_LIMIT = "5"
BLOCK_RECURRENCE_LIMIT_TARGET = 5  # Must match BLOCK_RECURRENCE_LIMIT in hermes_cli/kanban_db.py


def patch_block_recurrence_limit(
    log: Callable[[str], None] | None = None,
) -> bool:
    """Patch hermes_cli/kanban_db.py BLOCK_RECURRENCE_LIMIT to 5 (idempotent).

    Returns True if the limit is already at the target or was patched successfully.

    Resolves the Hermes installation directory by probing candidate paths
    until ``hermes-agent/hermes_cli/kanban_db.py`` is found.  Does NOT use
    project-local ``.hermes/`` directories — only the real Hermes install.
    """
    import os

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    # Candidate Hermes installation roots (ordered by likelihood).
    # We verify by checking that hermes-agent/hermes_cli/kanban_db.py exists.
    candidates: list[str] = []
    for env in ("HERMES_HOME", "HERMES_STATE_DIR"):
        raw = os.environ.get(env, "").strip()
        if raw:
            candidates.append(raw)
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            candidates.append(os.path.join(local_app, "hermes"))
    candidates.append(os.path.expanduser("~/.hermes"))
    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE", "").strip()
        if userprofile:
            candidates.append(os.path.join(userprofile, ".hermes"))

    target: str | None = None
    for root in candidates:
        probe = os.path.join(root, "hermes-agent", "hermes_cli", "kanban_db.py")
        if os.path.isfile(probe):
            target = probe
            break

    if target is None:
        tried = "\n".join(f"    {c}" for c in candidates)
        _log(
            f"   !  Could not find kanban_db.py in any candidate:\n{tried}\n"
            "   !  Patch BLOCK_RECURRENCE_LIMIT manually"
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


def verify_recurrence_limit_geq_failure_limit(
    log: Callable[[str], None] | None = None,
) -> bool:
    """Check BLOCK_RECURRENCE_LIMIT >= failure_limit from config.yaml.

    Reads ``kanban.failure_limit`` directly from ``$HERMES_HOME/config.yaml``
    (no subprocess — ``hermes config get`` doesn't exist).  Compares against
    BLOCK_RECURRENCE_LIMIT_TARGET.  Emits a non-blocking WARN when violated
    (never raises, never exits non-zero).

    Returns False when the invariant is violated (so callers can track it).
    """
    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    config_path = os.path.join(hermes_home, "config.yaml")
    config_limit = None
    try:
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            config_limit = int((cfg or {}).get("kanban", {}).get("failure_limit", 0)) or None
    except Exception:
        pass

    if config_limit is None:
        _log("   ?  Could not read kanban.failure_limit from config.yaml — skipping invariant check")
        return True  # can't verify — don't alarm

    if BLOCK_RECURRENCE_LIMIT_TARGET < config_limit:
        _log(
            f"   ⚠  WARN: BLOCK_RECURRENCE_LIMIT ({BLOCK_RECURRENCE_LIMIT_TARGET}) "
            f"< failure_limit ({config_limit}). "
            "Cards may be triaged before Six Sigma recovery exhausts. "
            f"Run: hermes config set kanban.failure_limit {BLOCK_RECURRENCE_LIMIT_TARGET}"
        )
        return False

    _log(f"   OK BLOCK_RECURRENCE_LIMIT ({BLOCK_RECURRENCE_LIMIT_TARGET}) >= failure_limit ({config_limit})")
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
