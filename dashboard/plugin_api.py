"""Kanban-Advanced dashboard plugin — backend API routes.

Mounted at /api/plugins/kanban-advanced/ by the dashboard plugin system.
Provides status, init, and update endpoints for the settings UI.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _find_project_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists() or (parent / ".env").exists():
            return parent
    return cwd


def _read_config(project_root: Path) -> dict:
    config_path = project_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if not config_path.exists():
        return {}
    config = {}
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            config[key.strip()] = val.strip().strip('"').strip("'")
    return config


def _read_env(project_root: Path) -> dict:
    env_file = project_root / ".env"
    if not env_file.exists():
        return {}
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _check_profiles() -> dict:
    result = {}
    try:
        r = _run([HERMES_BIN, "profile", "list"])
        profiles_output = r.stdout
    except Exception:
        profiles_output = ""

    for profile in ["worker", "orchestrator"]:
        info = {"exists": profile in profiles_output, "has_model": False, "model": ""}
        if info["exists"]:
            try:
                r = _run([HERMES_BIN, "-p", profile, "config", "show"])
                m = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", r.stdout)
                if m and m.group(1) and m.group(1) != "None":
                    info["has_model"] = True
                    info["model"] = m.group(1)
            except Exception:
                pass
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


@router.get("/status")
async def status():
    """GET /api/plugins/kanban-advanced/status"""
    project_root = _find_project_root()
    config = _read_config(project_root)
    env = _read_env(project_root)
    config_exists = bool(config)

    coding_agent = env.get("KANBAN_CODING_AGENT", config.get("coding_agent_binary", "agent"))

    return {
        "config_exists": config_exists,
        "config_path": str(project_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml") if config_exists else "",
        "working_branch": config.get("working_branch", "main"),
        "coding_agent": coding_agent,
        "coding_agent_binary": coding_agent,
        "max_turns": _get_max_turns(),
        "profiles": _check_profiles(),
        "gateway": _check_gateway(),
    }


@router.post("/init")
async def init(request: Request):
    """POST /api/plugins/kanban-advanced/init"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_root = _find_project_root()
    working_branch = body.get("working_branch", "main")
    coding_agent = body.get("coding_agent_binary", "agent")
    max_turns = body.get("max_turns", 180)

    output = []
    output.append(f"kanban-advanced init -- bootstrapping {project_root}")

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
    overlay_dir = project_root / ".hermes" / "kanban-overrides"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    config_file = overlay_dir / "kanban-config.yaml"
    config_file.write_text(
        f"# kanban-advanced config overlay\n"
        f"working_branch: {working_branch}\n"
        f"coding_agent_binary: {coding_agent}\n"
        f"skills_output_path: {os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))}/skills/kanban-advanced\n"
        f"profiles:\n"
        f"  orchestrator: orchestrator\n"
        f"  worker: worker\n"
    )
    output.append(f"   OK {config_file}")

    # Materialize skills
    plugin_root = Path(__file__).parent.parent
    skills_src = plugin_root / "plugin" / "skills"
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(skill_md.read_text())
                count += 1
        output.append(f"   OK {count} skills -> {skills_dst}")

    # Provision scripts
    scripts_src = plugin_root / "scripts"
    scripts_dst = hermes_home / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in ["auto_unblock.sh", "board_keeper.sh", "token_tracker.py"]:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(src.read_text())
            dst.chmod(0o755)
            output.append(f"   OK {script_name} -> {dst}")

    # Env
    env_file = project_root / ".env"
    env_content = ""
    if env_file.exists():
        env_content = env_file.read_text()
    if "HERMES_ENABLE_PROJECT_PLUGINS" not in env_content:
        env_content += "HERMES_ENABLE_PROJECT_PLUGINS=true\n"
    if "KANBAN_CODING_AGENT" not in env_content:
        env_content += f"KANBAN_CODING_AGENT={coding_agent}\n"
    env_file.write_text(env_content)
    output.append("   OK")

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


@router.post("/update")
async def update(request: Request):
    """POST /api/plugins/kanban-advanced/update"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_root = _find_project_root()
    config = _read_config(project_root)
    if not config:
        return {"error": "Config file not found. Run bootstrap first."}

    working_branch = body.get("working_branch", config.get("working_branch", "main"))
    coding_agent = body.get("coding_agent_binary", config.get("coding_agent_binary", "agent"))
    max_turns = body.get("max_turns", 180)

    output = []
    output.append("=== Updating settings ===")

    overlay_dir = project_root / ".hermes" / "kanban-overrides"
    config_file = overlay_dir / "kanban-config.yaml"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        f"# kanban-advanced config overlay\n"
        f"working_branch: {working_branch}\n"
        f"coding_agent_binary: {coding_agent}\n"
        f"skills_output_path: {os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))}/skills/kanban-advanced\n"
        f"profiles:\n"
        f"  orchestrator: orchestrator\n"
        f"  worker: worker\n"
    )
    output.append(f"   OK Updated {config_file}")

    env_file = project_root / ".env"
    env_content = env_file.read_text() if env_file.exists() else ""
    for key, val in [("HERMES_ENABLE_PROJECT_PLUGINS", "true"), ("KANBAN_CODING_AGENT", coding_agent)]:
        if key in env_content:
            env_content = re.sub(rf"^{key}=.*$", f"{key}={val}", env_content, flags=re.MULTILINE)
        else:
            env_content += f"\n{key}={val}\n"
    env_file.write_text(env_content)
    output.append(f"   OK Updated .env")

    current_turns = _get_max_turns()
    if current_turns < max_turns:
        _run([HERMES_BIN, "-p", "orchestrator", "config", "set", "agent.max_turns", str(max_turns)])
        output.append(f"   OK max_turns set to {max_turns}")

    plugin_root = Path(__file__).parent.parent
    skills_src = plugin_root / "plugin" / "skills"
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(skill_md.read_text())
                count += 1
        output.append(f"   OK {count} skills -> {skills_dst}")

    output.append("OK Settings updated")
    return {"success": True, "output": output}
