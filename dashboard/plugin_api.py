"""Kanban-Advanced dashboard plugin — backend API routes.

Mounted at /api/plugins/kanban-advanced/ by the dashboard plugin system.
Provides status, init, and save endpoints for the settings UI.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Request

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plugin.config_overlay import (  # noqa: E402
    DEFAULT_PLUGIN_NAME,
    PLUGIN_ROOT,
    build_overlay_yaml,
    detect_default_working_branch,
    normalize_optional_branch,
    normalize_policy_profile,
    overlay_path,
    read_overlay_config,
    resolve_branch_settings,
    resolve_coding_agent,
    resolve_hermes_home,
    resolve_plugin_install_dir,
    resolve_policy_profile,
    resolve_project_root,
    sync_project_env,
)

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")


def _run(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout, cwd=cwd,
    )


def _read_config(project_root: Path) -> dict:
    return read_overlay_config(overlay_path(project_root))


def _read_env(project_root: Path) -> dict:
    env_file = project_root / ".env"
    if not env_file.exists():
        return {}
    env = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _check_model_reachable(provider: str) -> bool | None:
    """Check provider auth status via `hermes auth status <provider>`.

    Returns True (logged in), False (logged out / expired), or None (unknown —
    command not available, provider doesn't use OAuth, or ambiguous output).
    None is rendered as yellow in the dashboard (configured but unverified).
    """
    if not provider:
        return None
    try:
        r = _run([HERMES_BIN, "auth", "status", provider], timeout=8)
        out = (r.stdout + r.stderr).lower()
        if any(k in out for k in ("logged out", "not logged", "expired", "invalid", "unauthenticated")):
            return False
        if any(k in out for k in ("logged in", "authenticated", "valid", "active")):
            return True
        # Command succeeded with no negative indicators — treat as reachable.
        if r.returncode == 0:
            return True
        return False
    except Exception:
        return None


def _check_profiles() -> dict:
    result = {}
    try:
        r = _run([HERMES_BIN, "profile", "list"])
        profiles_output = r.stdout
    except Exception:
        profiles_output = ""

    for profile in ["worker", "orchestrator"]:
        info: dict = {
            "exists": profile in profiles_output,
            "has_model": False,
            "model": "",
            "provider": "",
            "model_reachable": None,
        }
        if info["exists"]:
            try:
                r = _run([HERMES_BIN, "-p", profile, "config", "show"])
                m = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", r.stdout)
                if m and m.group(1) and m.group(1) != "None":
                    info["has_model"] = True
                    info["model"] = m.group(1)
                p = re.search(r"'provider':\s*'([^']+)'", r.stdout)
                if p:
                    info["provider"] = p.group(1)
            except Exception:
                pass

            if info["has_model"]:
                info["model_reachable"] = _check_model_reachable(info["provider"])

        result[profile] = info
    return result


def _check_gateway() -> dict:
    try:
        r = _run([HERMES_BIN, "gateway", "status"], timeout=10)
        running = r.returncode == 0
        outdated = "outdated" in r.stdout.lower()
        return {"running": running, "outdated": outdated}
    except Exception:
        return {"running": False, "outdated": False}


def _get_max_turns() -> int:
    try:
        r = _run([HERMES_BIN, "-p", "orchestrator", "config", "show"])
        mt = re.search(r"Max turns:\s*(\d+)", r.stdout)
        return int(mt.group(1)) if mt else 90
    except Exception:
        return 90


def _resolve_git_executable() -> str | None:
    found = shutil.which("git")
    if found:
        return found
    if os.name == "nt":
        prog = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(prog, "Git", "cmd", "git.exe"),
            os.path.join(prog, "Git", "bin", "git.exe"),
            os.path.join(prog_x86, "Git", "cmd", "git.exe"),
            os.path.join(prog_x86, "Git", "bin", "git.exe"),
        ]
        if local:
            candidates.extend(
                (
                    os.path.join(local, "Programs", "Git", "cmd", "git.exe"),
                    os.path.join(local, "Programs", "Git", "bin", "git.exe"),
                    os.path.join(local, "hermes", "git", "cmd", "git.exe"),
                    os.path.join(local, "hermes", "git", "bin", "git.exe"),
                )
            )
    else:
        candidates = ["/usr/bin/git", "/usr/local/bin/git", "/bin/git"]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _git_fetch_origin(install_dir: Path, git_exe: str) -> None:
    try:
        _run([git_exe, "fetch", "origin", "--quiet"], timeout=15, cwd=str(install_dir))
    except Exception:
        pass


def _git_resolve_upstream(install_dir: Path, git_exe: str) -> str | None:
    """First resolvable upstream ref for pull/reset."""
    for upstream in ("@{u}", "origin/main", "origin/master"):
        try:
            r = _run(
                [git_exe, "rev-parse", "--verify", upstream],
                timeout=10,
                cwd=str(install_dir),
            )
            if r.returncode == 0 and r.stdout.strip():
                return upstream
        except Exception:
            continue
    return None


def _git_behind_count(install_dir: Path, git_exe: str) -> int | None:
    """Commits the checkout is behind its upstream (after best-effort fetch)."""
    _git_fetch_origin(install_dir, git_exe)
    upstream = _git_resolve_upstream(install_dir, git_exe)
    if not upstream:
        return None
    try:
        r = _run(
            [git_exe, "rev-list", "--count", f"HEAD..{upstream}"],
            timeout=10,
            cwd=str(install_dir),
        )
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip())
    except Exception:
        pass
    return None


def _git_local_change_count(install_dir: Path, git_exe: str) -> int | None:
    """Count porcelain dirty entries (tracked edits + untracked paths)."""
    try:
        r = _run([git_exe, "status", "--porcelain"], timeout=15, cwd=str(install_dir))
        if r.returncode != 0:
            return None
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        return len(lines)
    except Exception:
        return None


def _git_discard_local_changes(
    install_dir: Path, git_exe: str, output: list[str]
) -> tuple[bool, str | None]:
    """Reset plugin install to HEAD — read-only upstream mirror on every platform."""
    r = _run([git_exe, "status", "--porcelain"], timeout=15, cwd=str(install_dir))
    dirty = (r.stdout or "").strip()
    if not dirty:
        return True, None

    lines = dirty.splitlines()
    output.append(
        f"   !  Discarding {len(lines)} local change(s) in plugin install "
        f"(edit your project repo, not {install_dir})"
    )
    for line in lines[:5]:
        output.append(f"      {line}")
    if len(lines) > 5:
        output.append(f"      ... and {len(lines) - 5} more")

    reset = _run([git_exe, "reset", "--hard", "HEAD"], timeout=30, cwd=str(install_dir))
    if reset.returncode != 0:
        err = (reset.stderr or reset.stdout or "git reset --hard failed").strip()
        return False, err

    # Untracked files can also block merge on some git versions.
    _run([git_exe, "clean", "-fd"], timeout=30, cwd=str(install_dir))
    return True, None


def _git_sync_to_upstream(
    install_dir: Path, git_exe: str, output: list[str]
) -> tuple[bool, str | None]:
    """Pull --ff-only, falling back to reset --hard <upstream> if needed."""
    _git_fetch_origin(install_dir, git_exe)
    upstream = _git_resolve_upstream(install_dir, git_exe)
    if not upstream:
        return False, "Could not resolve upstream (origin/main or tracking branch)"

    ok, err = _git_discard_local_changes(install_dir, git_exe, output)
    if not ok:
        return False, err

    r = _run([git_exe, "pull", "--ff-only"], timeout=120, cwd=str(install_dir))
    if r.stdout.strip():
        output.append(r.stdout.strip())
    if r.stderr.strip():
        output.append(r.stderr.strip())
    if r.returncode == 0:
        return True, None

    output.append(f"   !  pull --ff-only failed; resetting to {upstream}")
    hard = _run([git_exe, "reset", "--hard", upstream], timeout=30, cwd=str(install_dir))
    if hard.returncode != 0:
        err = (hard.stderr or hard.stdout or r.stderr or "git reset --hard failed").strip()
        return False, err
    if hard.stdout.strip():
        output.append(hard.stdout.strip())
    return True, None


def _materialize_plugin_assets(plugin_root: Path, hermes_home: Path) -> list[str]:
    """Copy bundled skills and cron scripts from plugin checkout into HERMES_HOME."""
    lines: list[str] = []
    skills_src = plugin_root / "plugin" / "skills"
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(
                    skill_md.read_text(encoding="utf-8"), encoding="utf-8"
                )
                count += 1
        lines.append(f"   OK {count} skills -> {skills_dst}")

    scripts_src = plugin_root / "scripts"
    scripts_dst = hermes_home / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in ["auto_unblock.sh", "board_keeper.sh", "token_tracker.py"]:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            dst.chmod(0o755)
            lines.append(f"   OK {script_name} -> {dst}")
    return lines


def _check_plugin_git_status() -> dict:
    """Whether the installed plugin git checkout has upstream commits to pull."""
    hermes_home = resolve_hermes_home()
    install_dir = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    base = {
        "hermes_home": str(hermes_home),
        "plugin_install_path": str(install_dir),
        "plugin_can_update": False,
        "plugin_up_to_date": None,
        "plugin_behind": None,
        "plugin_update_available": None,
        "plugin_local_changes": None,
    }
    if not (install_dir / ".git").is_dir():
        return base

    base["plugin_can_update"] = True
    git_exe = _resolve_git_executable()
    if not git_exe:
        return base

    base["plugin_local_changes"] = _git_local_change_count(install_dir, git_exe)

    behind = _git_behind_count(install_dir, git_exe)
    if behind is None:
        return base

    base["plugin_behind"] = behind
    base["plugin_update_available"] = behind > 0
    base["plugin_up_to_date"] = behind == 0
    return base


@router.get("/status")
async def status():
    """GET /api/plugins/kanban-advanced/status"""
    project_root = resolve_project_root()
    config = _read_config(project_root)
    env = _read_env(project_root)
    config_exists = overlay_path(project_root).is_file()

    coding_agent = resolve_coding_agent(project_root, env=env)

    detected_branch = detect_default_working_branch(project_root) or "main"

    return {
        "config_exists": config_exists,
        "project_root": str(project_root),
        "config_path": str(overlay_path(project_root)) if config_exists else "",
        "working_branch": config.get("working_branch") or detected_branch,
        "default_working_branch": detected_branch,
        "trigger_branch": config.get("trigger_branch", ""),
        "coding_agent": coding_agent,
        "coding_agent_binary": coding_agent,
        "policy_profile": resolve_policy_profile(project_root, env=env),
        "max_turns": _get_max_turns(),
        "profiles": _check_profiles(),
        "gateway": _check_gateway(),
        **_check_plugin_git_status(),
    }


@router.post("/init")
async def init(request: Request):
    """POST /api/plugins/kanban-advanced/init"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_root = resolve_project_root()
    config_file = overlay_path(project_root)
    existing_config = _read_config(project_root)
    env = _read_env(project_root)
    max_turns = body.get("max_turns", 180)

    if existing_config:
        working_branch, trigger_branch, kept = resolve_branch_settings(project_root)
        coding_agent = resolve_coding_agent(
            project_root,
            coding_agent=body.get("coding_agent_binary"),
            env=env,
        )
    else:
        working_branch, trigger_branch, kept = resolve_branch_settings(
            project_root,
            working_branch=body.get("working_branch"),
            trigger_branch=body.get("trigger_branch"),
            working_branch_specified="working_branch" in body,
            trigger_branch_specified="trigger_branch" in body,
        )
        coding_agent = resolve_coding_agent(
            project_root,
            coding_agent=body.get("coding_agent_binary"),
            env=env,
        )

    output = []
    output.append(f"kanban-advanced init -- bootstrapping {project_root}")
    output.append(f"   Working branch: {working_branch}")
    output.append(f"   Trigger branch: {trigger_branch or '(none — optional)'}")
    if "policy_profile" in body:
        policy_profile = normalize_policy_profile(body.get("policy_profile"))
    elif existing_config.get("policy_profile"):
        policy_profile = normalize_policy_profile(existing_config["policy_profile"])
        if existing_config:
            output.append("   Preserved governance profile from existing kanban-config.yaml")
    else:
        policy_profile = resolve_policy_profile(project_root, env=env)
    output.append(f"   Governance profile: {policy_profile}")
    if kept:
        output.append("   Preserved branch settings from existing kanban-config.yaml")

    # Profiles
    profiles = _check_profiles()
    for profile in ["worker", "orchestrator"]:
        if profiles[profile]["exists"]:
            output.append(f"   OK {profile}")
        else:
            r = _run([HERMES_BIN, "profile", "create", profile, "--clone"])
            if r.returncode == 0:
                output.append(f"   OK Created '{profile}'")
            else:
                output.append(f"   X Failed to create '{profile}': {r.stderr.strip()}")
                return {"success": False, "output": output, "error": f"Failed to create {profile} profile"}

    # Model config
    for profile in ["worker", "orchestrator"]:
        profiles = _check_profiles()
        if profiles[profile]["has_model"]:
            output.append(f"   OK {profile}: model configured")
        else:
            output.append(f"   !  {profile}: no model configured — copy from current profile")
            try:
                r = _run([HERMES_BIN, "config", "show"])
                dm = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", r.stdout)
                dp = re.search(r"'provider':\s*'([^']+)'", r.stdout)
                du = re.search(r"'base_url':\s*'([^']*)'", r.stdout)
                if dm and dp:
                    _run([HERMES_BIN, "-p", profile, "config", "set", "model.default", dm.group(1)])
                    _run([HERMES_BIN, "-p", profile, "config", "set", "model.provider", dp.group(1)])
                    if du and du.group(1):
                        _run([HERMES_BIN, "-p", profile, "config", "set", "model.base_url", du.group(1)])
                    output.append(f"   OK {profile} configured")
            except Exception as e:
                output.append(f"   !  Skipped: {e}")

    # Max turns
    current_turns = _get_max_turns()
    if current_turns >= max_turns:
        output.append(f"   OK orchestrator: max_turns = {current_turns}")
    else:
        _run([HERMES_BIN, "-p", "orchestrator", "config", "set", "agent.max_turns", str(max_turns)])
        output.append(f"   OK max_turns set to {max_turns}")

    # Coding agent
    coding_path = None
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if (Path(path_dir) / coding_agent).exists():
            coding_path = Path(path_dir) / coding_agent
            break
    if coding_path:
        output.append(f"   OK '{coding_agent}' found on PATH")
    else:
        output.append(f"   !  '{coding_agent}' not found on PATH")
    output.append(f"   coding_agent_binary: {coding_agent}")

    # Config overlay
    overlay_dir = config_file.parent
    overlay_dir.mkdir(parents=True, exist_ok=True)
    hermes_home = resolve_hermes_home()
    plugin_root = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    config_file.write_text(
        build_overlay_yaml(
            working_branch=working_branch,
            trigger_branch=trigger_branch,
            coding_agent=coding_agent,
            policy_profile=policy_profile,
            bundle_path=plugin_root,
            hermes_home=str(hermes_home),
            existing=existing_config,
        ),
        encoding="utf-8",
    )
    output.append(f"   OK {config_file}")

    # Materialize skills
    skills_src = PLUGIN_ROOT / "plugin" / "skills"
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(skill_md.read_text(encoding="utf-8"), encoding="utf-8")
                count += 1
        output.append(f"   OK {count} skills -> {skills_dst}")

    # Provision scripts
    scripts_src = PLUGIN_ROOT / "scripts"
    scripts_dst = hermes_home / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in ["auto_unblock.sh", "board_keeper.sh", "token_tracker.py"]:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(src.read_text())
            dst.chmod(0o755)
            output.append(f"   OK {script_name} -> {dst}")

    sync_project_env(
        project_root,
        {
            "HERMES_ENABLE_PROJECT_PLUGINS": "true",
            "KANBAN_CODING_AGENT": coding_agent,
            "KANBAN_POLICY_PROFILE": policy_profile,
        },
    )
    output.append("   OK")

    # Kanban config — disable built-in auto-decomposer so triage cards are
    # not rewritten by Hermes LLM before the orchestrator reviews them.
    r_ad = _run([HERMES_BIN, "config", "set", "kanban.auto_decompose", "false"])
    if r_ad.returncode == 0:
        output.append("   OK kanban.auto_decompose = false")
    else:
        output.append("   !  Could not set kanban.auto_decompose — set manually: hermes config set kanban.auto_decompose false")

    # Gateway
    gw = _check_gateway()
    if gw["running"]:
        if gw["outdated"]:
            output.append("   !  Gateway outdated — restart to update")
        else:
            output.append("   OK Gateway running")
    else:
        output.append("   !  Gateway not running")

    output.append("OK kanban-advanced is ready!")
    return {"success": True, "output": output}


@router.post("/save")
async def save(request: Request):
    """POST /api/plugins/kanban-advanced/save — persist dashboard settings to config (not plugin Pull)."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_root = resolve_project_root()
    config = _read_config(project_root)
    config_file = overlay_path(project_root)
    if not config_file.is_file():
        return {"error": "Config file not found. Run bootstrap first."}

    env = _read_env(project_root)
    working_branch = body.get("working_branch") or config.get("working_branch") or detect_default_working_branch(project_root) or "main"
    if "trigger_branch" in body:
        trigger_branch = normalize_optional_branch(body.get("trigger_branch"))
    else:
        trigger_branch = normalize_optional_branch(config.get("trigger_branch"))
    coding_agent = body.get("coding_agent_binary") or config.get("coding_agent_binary") or resolve_coding_agent(project_root, env=env)
    if "policy_profile" in body:
        policy_profile = normalize_policy_profile(body.get("policy_profile"))
    else:
        policy_profile = resolve_policy_profile(project_root, env=env)
    max_turns = body.get("max_turns", 180)

    output = []
    output.append("=== Saving settings ===")
    output.append(f"   Working branch: {working_branch}")
    output.append(f"   Trigger branch: {trigger_branch or '(none — optional)'}")
    output.append(f"   Governance profile: {policy_profile}")

    overlay_dir = config_file.parent
    overlay_dir.mkdir(parents=True, exist_ok=True)
    hermes_home = resolve_hermes_home()
    plugin_root = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    config_file.write_text(
        build_overlay_yaml(
            working_branch=working_branch,
            trigger_branch=trigger_branch,
            coding_agent=coding_agent,
            policy_profile=policy_profile,
            bundle_path=plugin_root,
            hermes_home=str(hermes_home),
            existing=config,
        ),
        encoding="utf-8",
    )
    output.append(f"   OK Saved {config_file}")

    sync_project_env(
        project_root,
        {
            "HERMES_ENABLE_PROJECT_PLUGINS": "true",
            "KANBAN_CODING_AGENT": coding_agent,
            "KANBAN_POLICY_PROFILE": policy_profile,
        },
    )
    output.append("   OK Saved .env")

    current_turns = _get_max_turns()
    if current_turns < max_turns:
        _run([HERMES_BIN, "-p", "orchestrator", "config", "set", "agent.max_turns", str(max_turns)])
        output.append(f"   OK max_turns set to {max_turns}")

    skills_src = PLUGIN_ROOT / "plugin" / "skills"
    hermes_home = resolve_hermes_home()
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(skill_md.read_text(encoding="utf-8"), encoding="utf-8")
                count += 1
        output.append(f"   OK {count} skills -> {skills_dst}")

    output.append("OK Settings saved")
    return {"success": True, "output": output}


@router.post("/update")
async def update_plugin():
    """POST /api/plugins/kanban-advanced/update — git pull plugin install + refresh materialized assets."""
    install_dir = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    output = [f"=== Updating plugin at {install_dir} ==="]

    if not (install_dir / ".git").is_dir():
        return {
            "success": False,
            "error": "Plugin install is not a git checkout — cannot pull.",
            "output": output,
        }

    git_exe = _resolve_git_executable()
    if not git_exe:
        return {"success": False, "error": "git not found on PATH", "output": output}

    behind_before = _git_behind_count(install_dir, git_exe)
    if behind_before is None:
        return {
            "success": False,
            "error": "Could not determine upstream — check git remote and tracking branch.",
            "output": output,
        }

    if behind_before == 0:
        output.append("   OK Already up to date")
        return {"success": True, "unchanged": True, "output": output}

    try:
        ok, err = _git_sync_to_upstream(install_dir, git_exe, output)
    except Exception as exc:
        logger.exception("plugin update: git sync failed")
        return {"success": False, "error": str(exc), "output": output}

    if not ok:
        return {"success": False, "error": err or "git sync failed", "output": output}

    hermes_home = resolve_hermes_home()
    output.extend(_materialize_plugin_assets(install_dir, hermes_home))
    output.append("OK Plugin updated")
    return {"success": True, "unchanged": False, "output": output}
