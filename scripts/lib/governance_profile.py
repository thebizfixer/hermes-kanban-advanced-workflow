#!/usr/bin/env python3
"""Resolve KANBAN_POLICY_PROFILE from CLI, kanban-config.yaml, env, or default.

Resolution order (keep in sync with plugin/config_overlay.resolve_policy_profile):
  CLI/body override > kanban-config.yaml policy_profile > KANBAN_POLICY_PROFILE > balanced
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

VALID_PROFILES = frozenset({"advisory", "balanced", "strict"})
DEFAULT_PROFILE = "balanced"


def normalize_profile(value: str | None) -> str:
    if not value:
        return DEFAULT_PROFILE
    v = value.strip().lower()
    return v if v in VALID_PROFILES else DEFAULT_PROFILE


def _read_overlay_key(config_path: Path, key: str) -> str | None:
    if not config_path.is_file():
        return None
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'") or None
    return None


def _find_config_path(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        repo_root = Path.cwd()
    for env_name in ("HERMES_KANBAN_CONFIG",):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    candidate = repo_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    return candidate if candidate.is_file() else None


def resolve_governance_profile(
    *,
    cli_override: str | None = None,
    repo_root: str | Path | None = None,
) -> str:
    if cli_override:
        return normalize_profile(cli_override)

    root = Path(repo_root).resolve() if repo_root else Path.cwd()
    config_path = _find_config_path(root)
    if config_path:
        from_config = _read_overlay_key(config_path, "policy_profile")
        if from_config:
            return normalize_profile(from_config)

    env_val = os.environ.get("KANBAN_POLICY_PROFILE", "").strip()
    if env_val:
        return normalize_profile(env_val)

    return DEFAULT_PROFILE


def warnings_are_blocking(profile: str) -> bool:
    return normalize_profile(profile) == "strict"


def failures_are_blocking(profile: str) -> bool:
    return normalize_profile(profile) != "advisory"


def should_notify_operator(profile: str) -> bool:
    return normalize_profile(profile) == "strict"


def emit_strict_notification(
    *,
    task_id: str,
    reason: str,
    failure_class: str = "governance_strict",
    repo_root: str | Path | None = None,
) -> None:
    """Persist strict-profile block for postmortem and bump intervention counter."""
    root = Path(repo_root).resolve() if repo_root else Path.cwd()
    logdir = root / ".hermes" / "kanban" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "failure_class": failure_class,
        "reason": reason,
        "profile": "strict",
    }
    with open(logdir / "interventions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    inc_script = Path(__file__).resolve().parent.parent / "kanban_intervention_inc.sh"
    if inc_script.is_file():
        try:
            subprocess.run(
                ["bash", str(inc_script)],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except Exception:
            pass
    print(
        f"[governance] Strict notification logged for {task_id} "
        f"({failure_class}) — gateway delivery via kanban-notify if configured"
    )
