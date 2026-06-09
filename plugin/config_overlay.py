"""Shared helpers for .hermes/kanban-overrides/kanban-config.yaml."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_WORKING_BRANCH = "main"
DEFAULT_TRIGGER_BRANCH = "production"
DEFAULT_CODING_AGENT = "agent"

OVERLAY_REL = Path(".hermes") / "kanban-overrides" / "kanban-config.yaml"

# Keys init/update always refresh; everything else is preserved on re-init.
_MANAGED_KEYS = frozenset({
    "schema_version",
    "working_branch",
    "trigger_branch",
    "orchestrator_profile",
    "worker_profile",
    "preflight_profiles",
    "coding_agent_binary",
    "bundle_path",
    "skills_output_path",
    "plan_memory_path",
    "escalation_max_attempts",
})


def overlay_path(project_root: Path) -> Path:
    return project_root / OVERLAY_REL


def read_overlay_config(config_path: Path) -> dict[str, str]:
    if not config_path.is_file():
        return {}
    config: dict[str, str] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            config[key.strip()] = val.strip().strip('"').strip("'")
    return config


def resolve_project_root(start: Path | None = None) -> Path:
    """Find the project root that owns kanban-config.yaml.

    Prefers explicit env overrides, then a tree walk that favors directories
    with an existing overlay config over bare .git/.env markers (avoids picking
    the plugin bundle or wrong clone when the gateway cwd shifts after update).
    """
    for env_name in ("KANBAN_PROJECT_ROOT", "HERMES_PROJECT_ROOT"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    config_env = os.environ.get("HERMES_KANBAN_CONFIG", "").strip()
    if config_env:
        return Path(config_env).expanduser().resolve().parent.parent.parent

    start = (start or Path.cwd()).resolve()
    config_hit: Path | None = None
    git_hit: Path | None = None
    env_hit: Path | None = None

    for parent in [start, *start.parents]:
        if overlay_path(parent).is_file() and config_hit is None:
            config_hit = parent
        if (parent / ".git").exists() and git_hit is None:
            git_hit = parent
        if (parent / ".env").exists() and env_hit is None:
            env_hit = parent

    return config_hit or git_hit or env_hit or start


def detect_git_branch(project_root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            branch = r.stdout.strip()
            if branch and branch != "HEAD":
                return branch
    except Exception:
        pass
    return None


def resolve_branch_settings(
    project_root: Path,
    *,
    working_branch: str | None = None,
    trigger_branch: str | None = None,
) -> tuple[str, str, bool]:
    """Return (working_branch, trigger_branch, used_existing_config)."""
    existing = read_overlay_config(overlay_path(project_root))
    used_existing = bool(existing)

    wb = working_branch or existing.get("working_branch") or detect_git_branch(project_root) or DEFAULT_WORKING_BRANCH
    tb = trigger_branch or existing.get("trigger_branch") or DEFAULT_TRIGGER_BRANCH
    return wb, tb, used_existing and (working_branch is None or trigger_branch is None)


def resolve_coding_agent(
    project_root: Path,
    *,
    coding_agent: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    if coding_agent:
        return coding_agent
    existing = read_overlay_config(overlay_path(project_root))
    if existing.get("coding_agent_binary"):
        return existing["coding_agent_binary"]
    env = env or {}
    return env.get("KANBAN_CODING_AGENT", DEFAULT_CODING_AGENT)


def build_overlay_yaml(
    *,
    working_branch: str,
    trigger_branch: str,
    coding_agent: str,
    bundle_path: Path | str,
    hermes_home: Path | str,
    existing: dict[str, str] | None = None,
) -> str:
    """Build overlay YAML, preserving user keys not managed by init/update."""
    existing = dict(existing or {})
    managed = {
        "schema_version": "1.0.0",
        "working_branch": working_branch,
        "trigger_branch": trigger_branch,
        "orchestrator_profile": existing.get("orchestrator_profile", "orchestrator"),
        "worker_profile": existing.get("worker_profile", "worker"),
        "preflight_profiles": existing.get("preflight_profiles", "worker,orchestrator"),
        "coding_agent_binary": coding_agent,
        "bundle_path": str(bundle_path),
        "skills_output_path": str(Path(hermes_home) / "skills" / "kanban-advanced"),
        "plan_memory_path": existing.get("plan_memory_path", ".hermes/kanban/memory"),
    }

    lines = ["# kanban-advanced config overlay"]
    for key, val in managed.items():
        if key == "preflight_profiles":
            lines.append(f'preflight_profiles: "{val}"')
        elif key == "schema_version":
            lines.append(f'schema_version: "{val}"')
        else:
            lines.append(f"{key}: {val}")

    # Preserve optional keys the user or example config may have set.
    skip = _MANAGED_KEYS | {"escalation_max_attempts"}
    for key in sorted(existing):
        if key in skip:
            continue
        val = existing[key]
        if val:
            lines.append(f"{key}: {val}")

    lines.extend([
        "escalation_max_attempts:",
        "  coding_agent: 3",
        "  worker: 3",
        "  orchestrator: 3",
        "",
    ])
    return "\n".join(lines)
