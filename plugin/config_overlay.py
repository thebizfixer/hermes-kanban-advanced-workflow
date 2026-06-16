"""Shared helpers for .hermes/kanban-overrides/kanban-config.yaml."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_WORKING_BRANCH = "main"
DEFAULT_CODING_AGENT = "agent"
DEFAULT_CODING_AGENT_MODEL = "auto"
DEFAULT_POLICY_PROFILE = "balanced"
DEFAULT_NOTIFY_LIFECYCLE = True
DEFAULT_SUBAGENT_GATE_ENABLED = True
VALID_POLICY_PROFILES = frozenset({"advisory", "balanced", "strict"})

DEFAULT_WORKER_PROFILE = "kanban-advanced-worker"
DEFAULT_ORCHESTRATOR_PROFILE = "kanban-advanced-orchestrator"
LEGACY_WORKER_PROFILE = "worker"
LEGACY_ORCHESTRATOR_PROFILE = "orchestrator"

PROFILE_SKILL_SETS_BY_ROLE: dict[str, frozenset[str]] = {
    "worker": frozenset({
        "kanban-git",
        "kanban-worker",
        "kanban-worker-governance",
    }),
    "orchestrator": frozenset({
        "kanban-advanced",
        "kanban-cleanup",
        "kanban-notify",
        "kanban-orchestrator",
        "kanban-orchestrator-governance",
        "kanban-planning",
        "kanban-postmortem",
        "kanban-preflight",
        "kanban-reconciliation",
    }),
}

OVERLAY_REL = Path(".hermes") / "kanban-overrides" / "kanban-config.yaml"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLUGIN_NAME = "kanban-advanced"

# Keys init/save always refresh; everything else is preserved on re-init.
_MANAGED_KEYS = frozenset({
    "schema_version",
    "working_branch",
    "trigger_branch",
    "policy_profile",
    "notify_lifecycle",
    "orchestrator_profile",
    "worker_profile",
    "preflight_profiles",
    "coding_agent_binary",
    "coding_agent_model",
    "bundle_path",
    "skills_output_path",
    "plan_memory_path",
    "escalation_max_attempts",
    "final_audit_max_remediation_rounds",
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


def normalize_optional_branch(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def resolve_project_root(start: Path | None = None) -> Path:
    """Find the project root that owns kanban-config.yaml."""
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


def resolve_hermes_home(project_root: Path | str | None = None) -> Path:
    """Resolve Hermes state directory ($HERMES_HOME / $HERMES_STATE_DIR / defaults).

    When running inside Hermes Agent, delegates to ``hermes_constants.get_hermes_home``.
    Otherwise mirrors ``scripts/lib/hermes_home.sh`` resolution order, then project-local
    ``<project>/.hermes`` (common for project-scoped plugins), then Windows
    ``%LOCALAPPDATA%/hermes``.
    """
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home().expanduser().resolve()
    except ImportError:
        pass

    for env_name in ("HERMES_HOME", "HERMES_STATE_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    roots: list[Path] = []
    if project_root is not None:
        roots.append(Path(project_root).expanduser().resolve())
    else:
        try:
            roots.append(resolve_project_root())
        except Exception:
            pass

    for root in roots:
        project_hermes = root / ".hermes"
        if project_hermes.is_dir():
            return project_hermes.resolve()

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            local_hermes = Path(local) / "hermes"
            if local_hermes.is_dir():
                return local_hermes.resolve()

    # Mirror scripts/lib/hermes_home.sh — data dir only (not %LOCALAPPDATA%/hermes install tree).
    home = Path.home()
    home_hermes = home / ".hermes"
    userprofile_hermes: Path | None = None
    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE", "").strip()
        if userprofile:
            userprofile_hermes = Path(userprofile) / ".hermes"

    for candidate in (home_hermes, userprofile_hermes):
        if candidate and candidate.is_dir():
            return candidate.resolve()
    if userprofile_hermes is not None:
        return userprofile_hermes.resolve()
    return home_hermes.resolve()


def resolve_plugin_skills_src(plugin_name: str = DEFAULT_PLUGIN_NAME) -> Path:
    """Installed plugin checkout's skill bundle (``plugin/skills``)."""
    return resolve_plugin_install_dir(plugin_name) / "plugin" / "skills"


def resolve_plugin_prompts_src(plugin_name: str = DEFAULT_PLUGIN_NAME) -> Path:
    """Installed plugin checkout's role prompts (``plugin/data/prompts``)."""
    return resolve_plugin_install_dir(plugin_name) / "plugin" / "data" / "prompts"


def resolve_plugin_install_dir(plugin_name: str = DEFAULT_PLUGIN_NAME) -> Path:
    """Git checkout path for the plugin (``$HERMES_HOME/plugins/<name>`` when installed)."""
    installed = resolve_hermes_home() / "plugins" / plugin_name
    if installed.is_dir():
        return installed.resolve()
    return PLUGIN_ROOT.resolve()


def _git_output(project_root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            out = r.stdout.strip()
            return out if out else None
    except Exception:
        pass
    return None


def _strip_remote_branch(ref: str) -> str:
    if ref.startswith("refs/remotes/origin/"):
        return ref[len("refs/remotes/origin/") :]
    if ref.startswith("origin/"):
        return ref[len("origin/") :]
    return ref


def detect_default_working_branch(project_root: Path) -> str | None:
    """Best-effort default integration branch (IDE / origin default / local HEAD)."""
    upstream = _git_output(project_root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if upstream:
        return _strip_remote_branch(upstream)

    origin_default = _git_output(project_root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if origin_default:
        return _strip_remote_branch(origin_default)

    head = _git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    if head and head != "HEAD":
        return head
    return None


def resolve_branch_settings(
    project_root: Path,
    *,
    working_branch: str | None = None,
    trigger_branch: str | None = None,
    working_branch_specified: bool = False,
    trigger_branch_specified: bool = False,
) -> tuple[str, str | None, bool]:
    """Return (working_branch, trigger_branch|None, preserved_from_existing)."""
    existing = read_overlay_config(overlay_path(project_root))
    preserved = bool(existing) and not working_branch_specified and not trigger_branch_specified

    if working_branch_specified and normalize_optional_branch(working_branch):
        wb = normalize_optional_branch(working_branch) or DEFAULT_WORKING_BRANCH
    elif existing.get("working_branch"):
        wb = existing["working_branch"]
    else:
        wb = detect_default_working_branch(project_root) or DEFAULT_WORKING_BRANCH

    if trigger_branch_specified:
        tb = normalize_optional_branch(trigger_branch)
    elif existing.get("trigger_branch"):
        tb = normalize_optional_branch(existing.get("trigger_branch"))
    else:
        tb = None

    return wb, tb, preserved


def _upgrade_legacy_profile_name(name: str) -> str:
    if name == LEGACY_WORKER_PROFILE:
        return DEFAULT_WORKER_PROFILE
    if name == LEGACY_ORCHESTRATOR_PROFILE:
        return DEFAULT_ORCHESTRATOR_PROFILE
    return name


def resolve_dispatch_profiles(
    existing: dict[str, str] | None = None,
) -> tuple[str, str, str]:
    """Return (worker_profile, orchestrator_profile, preflight_profiles)."""
    existing = existing or {}
    worker = _upgrade_legacy_profile_name(
        existing.get("worker_profile") or DEFAULT_WORKER_PROFILE
    )
    orchestrator = _upgrade_legacy_profile_name(
        existing.get("orchestrator_profile") or DEFAULT_ORCHESTRATOR_PROFILE
    )
    preflight_raw = existing.get("preflight_profiles")
    if preflight_raw:
        preflight = ",".join(
            _upgrade_legacy_profile_name(part.strip())
            for part in preflight_raw.split(",")
            if part.strip()
        )
    else:
        preflight = f"{worker},{orchestrator}"
    return worker, orchestrator, preflight


def normalize_policy_profile(value: str | None) -> str:
    if not value:
        return DEFAULT_POLICY_PROFILE
    v = value.strip().lower()
    return v if v in VALID_POLICY_PROFILES else DEFAULT_POLICY_PROFILE


def resolve_policy_profile(
    project_root: Path,
    *,
    policy_profile: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Explicit arg > kanban-config.yaml > .env > balanced."""
    if policy_profile:
        return normalize_policy_profile(policy_profile)
    existing = read_overlay_config(overlay_path(project_root))
    if existing.get("policy_profile"):
        return normalize_policy_profile(existing["policy_profile"])
    env = env or {}
    if env.get("KANBAN_POLICY_PROFILE"):
        return normalize_policy_profile(env["KANBAN_POLICY_PROFILE"])
    return DEFAULT_POLICY_PROFILE


def normalize_notify_lifecycle(value: str | bool | None) -> bool:
    if value is None:
        return DEFAULT_NOTIFY_LIFECYCLE
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("false", "0", "no", "off"):
        return False
    if s in ("true", "1", "yes", "on"):
        return True
    return DEFAULT_NOTIFY_LIFECYCLE


def resolve_notify_lifecycle(
    project_root: Path,
    *,
    notify_lifecycle: str | bool | None = None,
    config: dict[str, str] | None = None,
) -> bool:
    """Explicit arg > kanban-config.yaml > default true."""
    if notify_lifecycle is not None:
        return normalize_notify_lifecycle(notify_lifecycle)
    if config is None:
        config = read_overlay_config(overlay_path(project_root))
    if "notify_lifecycle" in config:
        return normalize_notify_lifecycle(config["notify_lifecycle"])
    return DEFAULT_NOTIFY_LIFECYCLE


def _parse_subagent_gate_enabled_from_text(text: str) -> bool | None:
    """Return enabled flag when subagent_gate block is present; else None (use default)."""
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("subagent_gate:"):
            in_block = True
            continue
        if in_block:
            if ":" in stripped and not line[:1].isspace():
                break
            if stripped.startswith("enabled:"):
                val = stripped.split(":", 1)[1].strip().strip('"').strip("'").lower()
                return val in ("true", "1", "yes", "on")
    return None


def normalize_subagent_gate_enabled(value: str | bool | None) -> bool:
    if value is None:
        return DEFAULT_SUBAGENT_GATE_ENABLED
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("false", "0", "no", "off"):
        return False
    if s in ("true", "1", "yes", "on"):
        return True
    return DEFAULT_SUBAGENT_GATE_ENABLED


def resolve_subagent_gate_enabled(
    project_root: Path,
    *,
    subagent_gate_enabled: str | bool | None = None,
    config: dict[str, str] | None = None,
) -> bool:
    """Explicit arg > kanban-config.yaml subagent_gate.enabled > default true."""
    if subagent_gate_enabled is not None:
        return normalize_subagent_gate_enabled(subagent_gate_enabled)
    config_path = overlay_path(project_root)
    if config_path.is_file():
        parsed = _parse_subagent_gate_enabled_from_text(
            config_path.read_text(encoding="utf-8")
        )
        if parsed is not None:
            return parsed
    if config and "subagent_gate_enabled" in config:
        return normalize_subagent_gate_enabled(config["subagent_gate_enabled"])
    return DEFAULT_SUBAGENT_GATE_ENABLED


def sync_dispatch_runtime_env(
    project_root: Path,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Persist HOME (and related) so gateway workers can resolve CLI credentials."""
    from plugin.coding_agent_env import dispatch_runtime_env_updates

    updates = dispatch_runtime_env_updates(env)
    if updates:
        sync_project_env(project_root, updates)
    return updates


def sync_project_env(project_root: Path, updates: dict[str, str]) -> None:
    """Upsert KEY=value lines in project .env."""
    import re

    env_file = project_root / ".env"
    content = env_file.read_text(encoding="utf-8") if env_file.is_file() else ""
    for key, val in updates.items():
        pattern = rf"^{re.escape(key)}=.*$"
        line = f"{key}={val}"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, line, content, flags=re.MULTILINE)
        else:
            if content and not content.endswith("\n"):
                content += "\n"
            content += line + "\n"
    env_file.write_text(content, encoding="utf-8")


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


def resolve_coding_agent_model(
    project_root: Path,
    *,
    coding_agent_model: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    from plugin.coding_agent import normalize_coding_agent_model

    if coding_agent_model is not None:
        return normalize_coding_agent_model(coding_agent_model)
    existing = read_overlay_config(overlay_path(project_root))
    if existing.get("coding_agent_model"):
        return normalize_coding_agent_model(existing["coding_agent_model"])
    env = env or {}
    if env.get("KANBAN_CODING_AGENT_MODEL"):
        return normalize_coding_agent_model(env["KANBAN_CODING_AGENT_MODEL"])
    return DEFAULT_CODING_AGENT_MODEL


def build_overlay_yaml(
    *,
    working_branch: str,
    trigger_branch: str | None,
    coding_agent: str,
    coding_agent_model: str | None = None,
    policy_profile: str = DEFAULT_POLICY_PROFILE,
    notify_lifecycle: str | bool | None = None,
    bundle_path: Path | str,
    hermes_home: Path | str,
    existing: dict[str, str] | None = None,
    project_root: Path | None = None,
) -> str:
    """Build overlay YAML, preserving user keys not managed by init/save."""
    from plugin.coding_agent import normalize_coding_agent_model

    existing = dict(existing or {})
    worker_profile, orchestrator_profile, preflight_profiles = resolve_dispatch_profiles(
        existing
    )
    model_value = normalize_coding_agent_model(
        coding_agent_model
        if coding_agent_model is not None
        else existing.get("coding_agent_model")
    )
    managed: dict[str, str] = {
        "schema_version": "1.0.0",
        "working_branch": working_branch,
        "policy_profile": normalize_policy_profile(
            policy_profile or existing.get("policy_profile")
        ),
        "notify_lifecycle": "true"
        if normalize_notify_lifecycle(
            notify_lifecycle
            if notify_lifecycle is not None
            else existing.get("notify_lifecycle")
        )
        else "false",
        "orchestrator_profile": orchestrator_profile,
        "worker_profile": worker_profile,
        "preflight_profiles": preflight_profiles,
        "coding_agent_binary": coding_agent,
        "coding_agent_model": model_value,
        "bundle_path": str(bundle_path),
        "skills_output_path": str(Path(hermes_home) / "skills" / "kanban-advanced"),
        "plan_memory_path": existing.get("plan_memory_path", ".hermes/kanban/memory"),
    }
    if trigger_branch:
        managed["trigger_branch"] = trigger_branch

    subagent_enabled = DEFAULT_SUBAGENT_GATE_ENABLED
    if project_root is not None:
        subagent_enabled = resolve_subagent_gate_enabled(project_root)

    lines = ["# kanban-advanced config overlay"]
    for key, val in managed.items():
        if key == "preflight_profiles":
            lines.append(f'preflight_profiles: "{val}"')
        elif key in ("schema_version", "policy_profile", "coding_agent_model"):
            lines.append(f'{key}: "{val}"')
        elif key == "notify_lifecycle":
            lines.append(f"notify_lifecycle: {val}")
        else:
            lines.append(f"{key}: {val}")

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
        "subagent_gate:",
        f"  enabled: {'true' if subagent_enabled else 'false'}",
        "  timeouts:",
        "    plan_gate: 30",
        "    env_gate: 120",
        "    infra_gate: 15",
        "    plan_parse: 60",
        "    cron_setup: 30",
        "",
    ])
    return "\n".join(lines)
