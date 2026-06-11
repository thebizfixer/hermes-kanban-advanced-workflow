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
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Request

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plugin.config_overlay import (  # noqa: E402
    DEFAULT_ORCHESTRATOR_PROFILE,
    DEFAULT_PLUGIN_NAME,
    DEFAULT_WORKER_PROFILE,
    build_overlay_yaml,
    detect_default_working_branch,
    normalize_optional_branch,
    normalize_policy_profile,
    overlay_path,
    read_overlay_config,
    resolve_branch_settings,
    resolve_coding_agent,
    resolve_coding_agent_model,
    resolve_dispatch_profiles,
    resolve_hermes_home,
    resolve_plugin_install_dir,
    resolve_plugin_skills_src,
    resolve_policy_profile,
    resolve_project_root,
    sync_project_env,
)
from plugin.coding_agent import (  # noqa: E402
    SMOKE_TIMEOUT_SECONDS,
    check_coding_agent_cli,
    list_models_for_binary,
    model_display_label,
    normalize_coding_agent_model,
)
from plugin.hermes_model_config import (  # noqa: E402
    copy_active_model_to_profile,
    read_model_config_from_config_show,
    profile_has_model_config,
)
from plugin.profile_bootstrap import (  # noqa: E402
    dispatch_profile_names,
    ensure_dispatch_profiles,
    reconcile_dispatch_profiles,
)

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")

_status_cache: dict[str, tuple[float, object]] = {}
_status_cache_lock = Lock()
_TTL_GIT_BEHIND = 300.0
_TTL_MODEL_PROBE = 180.0


def _cache_get(key: str, ttl: float):
    with _status_cache_lock:
        entry = _status_cache.get(key)
        if entry and (time.monotonic() - entry[0]) < ttl:
            return entry[1]
    return None


def _cache_set(key: str, value: object) -> None:
    with _status_cache_lock:
        _status_cache[key] = (time.monotonic(), value)


def _invalidate_status_cache() -> None:
    with _status_cache_lock:
        _status_cache.clear()


def _parse_bool_query(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() not in ("0", "false", "no", "")


def _hermes_subprocess_env(hermes_home: Path | str) -> dict[str, str]:
    return {**os.environ, "HERMES_HOME": str(hermes_home)}


def _run(
    cmd: list[str], timeout: int = 30, cwd: str | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout, cwd=cwd, env=env,
    )


def _run_coding_agent_cli(
    cmd: list[str], timeout: int = SMOKE_TIMEOUT_SECONDS, cwd: str | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Subprocess runner for coding-CLI smoke/list — longer timeout than generic _run."""
    return _run(cmd, timeout=timeout, cwd=cwd, env=env)


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


def _check_model_reachable(profile: str) -> bool | None:
    """Ping the model configured for *profile* via a minimal chat query.

    Returns True (model responded), False (model name invalid or auth failed),
    or None (timed out or ambiguous — yellow in dashboard).
    No --yolo flag is needed; "say ok" never triggers tool calls.
    """
    if not profile:
        return None
    try:
        r = _run([HERMES_BIN, "-p", profile, "chat", "-q", "say ok"], timeout=20)
        out = (r.stdout + r.stderr).lower()
        if r.returncode == 0:
            return True
        if any(k in out for k in (
            "model not found", "no such model", "unknown model",
            "invalid model", "does not exist", "not available",
            "authentication", "unauthorized", "401", "403",
            "token", "expired", "api key",
        )):
            return False
        # Non-zero exit with no diagnostic keywords — treat as unknown (yellow).
        return None
    except Exception:
        return None


def _dispatch_profile_list(project_root: Path | None = None) -> list[str]:
    if project_root is None:
        project_root = resolve_project_root()
    worker, orchestrator, _ = resolve_dispatch_profiles(
        read_overlay_config(overlay_path(project_root))
    )
    return [worker, orchestrator]


def _profile_config_show(profile: str, *, cached: str | None = None) -> str:
    if cached is not None:
        return cached
    try:
        r = _run([HERMES_BIN, "-p", profile, "config", "show"])
        return r.stdout
    except Exception:
        return ""


def _max_turns_from_config_show(stdout: str) -> int:
    mt = re.search(r"Max turns:\s*(\d+)", stdout)
    return int(mt.group(1)) if mt else 90


def _check_profiles(
    project_root: Path | None = None,
    *,
    probe_models: bool = False,
    config_show_cache: dict[str, str] | None = None,
) -> dict:
    result = {}
    config_show_cache = config_show_cache or {}
    try:
        r = _run([HERMES_BIN, "profile", "list"])
        profiles_output = r.stdout
    except Exception:
        profiles_output = ""

    for profile in _dispatch_profile_list(project_root):
        info: dict = {
            "exists": profile in profiles_output,
            "has_model": False,
            "model": "",
            "provider": "",
            "model_reachable": None,
        }
        if info["exists"]:
            stdout = _profile_config_show(
                profile, cached=config_show_cache.get(profile)
            )
            model_cfg = read_model_config_from_config_show(stdout)
            if profile_has_model_config(model_cfg):
                info["has_model"] = True
                info["model"] = model_cfg.get("default", "")
            if model_cfg.get("provider"):
                info["provider"] = model_cfg["provider"]

            if info["has_model"] and probe_models:
                cache_key = f"model_reachable:{profile}"
                cached = _cache_get(cache_key, _TTL_MODEL_PROBE)
                if cached is not None:
                    info["model_reachable"] = cached
                else:
                    info["model_reachable"] = _check_model_reachable(profile)
                    _cache_set(cache_key, info["model_reachable"])

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


def _get_max_turns(
    project_root: Path | None = None,
    *,
    orchestrator_config_show: str | None = None,
) -> int:
    if orchestrator_config_show is not None:
        return _max_turns_from_config_show(orchestrator_config_show)
    _, orchestrator_profile, _ = resolve_dispatch_profiles(
        read_overlay_config(overlay_path(project_root or resolve_project_root()))
    )
    return _max_turns_from_config_show(_profile_config_show(orchestrator_profile))


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


def _git_behind_count(
    install_dir: Path, git_exe: str, *, fetch: bool = True
) -> int | None:
    """Commits the checkout is behind its upstream."""
    cache_key = f"git_behind:{install_dir}"
    if not fetch:
        cached = _cache_get(cache_key, _TTL_GIT_BEHIND)
        if cached is not None:
            return cached  # type: ignore[return-value]

    if fetch:
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
            behind = int(r.stdout.strip())
            _cache_set(cache_key, behind)
            return behind
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
    for script_name in [
        "auto_unblock.sh",
        "board_keeper.sh",
        "token_tracker.py",
        "coding_agent_invoke.sh",
    ]:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            dst.chmod(0o755)
            lines.append(f"   OK {script_name} -> {dst}")
    return lines


def _check_plugin_git_status(*, fetch: bool = True) -> dict:
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

    behind = _git_behind_count(install_dir, git_exe, fetch=fetch)
    if behind is None:
        return base

    base["plugin_behind"] = behind
    base["plugin_update_available"] = behind > 0
    base["plugin_up_to_date"] = behind == 0
    return base


def _build_status(*, probe: bool = False, git_fetch: bool = False) -> dict:
    project_root = resolve_project_root()
    config = _read_config(project_root)
    env = _read_env(project_root)
    config_exists = overlay_path(project_root).is_file()

    coding_agent = resolve_coding_agent(project_root, env=env)
    coding_agent_model = resolve_coding_agent_model(project_root, env=env)
    coding_agent_cli = check_coding_agent_cli(
        coding_agent,
        coding_agent_model,
        _run_coding_agent_cli,
        probe=probe,
        cache_get=_cache_get,
        cache_set=_cache_set,
        probe_ttl=_TTL_MODEL_PROBE,
    )
    coding_agent_cli["model_label"] = model_display_label(coding_agent_model)

    configured_branch = config.get("working_branch")
    if configured_branch:
        detected_branch = configured_branch
    else:
        detected_branch = detect_default_working_branch(project_root) or "main"

    worker_profile, orchestrator_profile, _ = resolve_dispatch_profiles(config)
    orch_config_show = _profile_config_show(orchestrator_profile)

    return {
        "config_exists": config_exists,
        "project_root": str(project_root),
        "config_path": str(overlay_path(project_root)) if config_exists else "",
        "working_branch": configured_branch or detected_branch,
        "default_working_branch": detected_branch,
        "trigger_branch": config.get("trigger_branch", ""),
        "coding_agent": coding_agent,
        "coding_agent_binary": coding_agent,
        "coding_agent_model": coding_agent_model,
        "coding_agent_cli": coding_agent_cli,
        "policy_profile": resolve_policy_profile(project_root, env=env),
        "max_turns": _get_max_turns(
            project_root, orchestrator_config_show=orch_config_show
        ),
        "profiles": _check_profiles(
            project_root,
            probe_models=probe,
            config_show_cache={orchestrator_profile: orch_config_show},
        ),
        "dispatch_profiles": {
            "worker": worker_profile,
            "orchestrator": orchestrator_profile,
        },
        "gateway": _check_gateway(),
        "status_checks": {
            "probe": probe,
            "git_fetch": git_fetch,
        },
        **_check_plugin_git_status(fetch=git_fetch),
    }


@router.get("/status")
async def status(request: Request):
    """GET /api/plugins/kanban-advanced/status"""
    probe = _parse_bool_query(request.query_params.get("probe"))
    git_fetch = _parse_bool_query(request.query_params.get("git_fetch"))
    return _build_status(probe=probe, git_fetch=git_fetch)


@router.get("/coding-agent/models")
async def coding_agent_models(request: Request):
    """GET /api/plugins/kanban-advanced/coding-agent/models?binary=agent"""
    binary = (request.query_params.get("binary") or "agent").strip()
    return list_models_for_binary(binary, _run_coding_agent_cli)


def _append_coding_agent_cli_log(
    output: list[str],
    binary: str,
    model: str,
    *,
    probe: bool = True,
) -> None:
    cli = check_coding_agent_cli(
        binary,
        model,
        _run_coding_agent_cli,
        probe=probe,
        cache_get=_cache_get if probe else None,
        cache_set=_cache_set if probe else None,
        probe_ttl=_TTL_MODEL_PROBE,
    )
    label = model_display_label(model)
    if not cli.get("on_path"):
        output.append(f"   !  '{binary}' not found on PATH")
        return
    output.append(f"   OK '{binary}' found on PATH")
    output.append(f"   coding_agent_binary: {binary}")
    output.append(f"   coding_agent_model: {model} ({label})")
    if not probe:
        return
    reachable = cli.get("model_reachable")
    if reachable is True:
        output.append(f"   OK coding CLI reachable ({label})")
    elif reachable is False:
        output.append(f"   !  coding CLI auth/model check failed ({label})")
    else:
        output.append(f"   !  coding CLI smoke inconclusive ({label})")


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
        coding_agent_model = resolve_coding_agent_model(
            project_root,
            coding_agent_model=body.get("coding_agent_model"),
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
        coding_agent_model = normalize_coding_agent_model(
            body.get("coding_agent_model", "auto")
        )

    output = []
    output.append(f"kanban-advanced init -- bootstrapping {project_root}")
    hermes_home_pre = resolve_hermes_home(project_root)
    output.append(f"   HERMES_HOME: {hermes_home_pre}")
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

    worker_profile, orchestrator_profile = dispatch_profile_names(existing_config)
    dispatch_profiles = [worker_profile, orchestrator_profile]

    # Profiles (create or rename legacy short names) — model config below needs
    # the prefixed profiles to exist; full reconcile (seed + verify) runs later.
    if not ensure_dispatch_profiles(
        _run,
        HERMES_BIN,
        hermes_home=hermes_home_pre,
        force=True,
        log=output.append,
    ):
        return {
            "success": False,
            "output": output,
            "error": "Failed to ensure dispatch profiles",
        }

    init_env = _hermes_subprocess_env(hermes_home_pre)

    # Model config
    for profile in dispatch_profiles:
        profiles = _check_profiles(project_root)
        if profiles[profile]["has_model"]:
            output.append(f"   OK {profile}: model configured")
        else:
            output.append(f"   !  {profile}: no model configured — copy from current profile")
            try:
                copied = copy_active_model_to_profile(
                    _run, HERMES_BIN, profile, env=init_env
                )
                if copied:
                    output.append(f"   OK {profile} configured")
                else:
                    output.append(f"   !  Skipped: active profile has no model in config.yaml")
            except Exception as e:
                output.append(f"   !  Skipped: {e}")

    # Max turns
    current_turns = _get_max_turns(project_root)
    if current_turns >= max_turns:
        output.append(f"   OK {orchestrator_profile}: max_turns = {current_turns}")
    else:
        _run([HERMES_BIN, "-p", orchestrator_profile, "config", "set", "agent.max_turns", str(max_turns)], env=init_env)
        output.append(f"   OK max_turns set to {max_turns}")

    # Coding agent binary + model (+ smoke when binary is on PATH)
    _append_coding_agent_cli_log(
        output, coding_agent, coding_agent_model, probe=True
    )

    # Config overlay
    overlay_dir = config_file.parent
    overlay_dir.mkdir(parents=True, exist_ok=True)
    hermes_home = hermes_home_pre
    plugin_root = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    config_file.write_text(
        build_overlay_yaml(
            working_branch=working_branch,
            trigger_branch=trigger_branch,
            coding_agent=coding_agent,
            coding_agent_model=coding_agent_model,
            policy_profile=policy_profile,
            bundle_path=plugin_root,
            hermes_home=str(hermes_home),
            existing=existing_config,
        ),
        encoding="utf-8",
    )
    output.append(f"   OK {config_file}")

    # Materialize skills
    skills_src = resolve_plugin_skills_src(DEFAULT_PLUGIN_NAME)
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
    else:
        output.append(f"   X Skills not found at {skills_src}")

    # Reconcile profiles: rename → seed role-only skills → verify (+ fix retry)
    worker_profile, orchestrator_profile = dispatch_profile_names(
        read_overlay_config(config_file)
    )
    if not reconcile_dispatch_profiles(
        _run,
        HERMES_BIN,
        hermes_home,
        skills_src,
        worker_profile,
        orchestrator_profile,
        force=True,
        log=output.append,
    ):
        return {
            "success": False,
            "output": output,
            "error": "Profile reconciliation/verification failed",
        }

    # Provision scripts
    scripts_src = plugin_root / "scripts"
    scripts_dst = hermes_home / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in [
        "auto_unblock.sh",
        "board_keeper.sh",
        "token_tracker.py",
        "coding_agent_invoke.sh",
    ]:
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
            "KANBAN_CODING_AGENT_MODEL": coding_agent_model,
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
    _invalidate_status_cache()
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
    if "coding_agent_model" in body:
        coding_agent_model = normalize_coding_agent_model(body.get("coding_agent_model"))
    else:
        coding_agent_model = resolve_coding_agent_model(project_root, env=env)
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
    _append_coding_agent_cli_log(
        output, coding_agent, coding_agent_model, probe=True
    )

    overlay_dir = config_file.parent
    overlay_dir.mkdir(parents=True, exist_ok=True)
    hermes_home = resolve_hermes_home(project_root)
    plugin_root = resolve_plugin_install_dir(DEFAULT_PLUGIN_NAME)
    config_file.write_text(
        build_overlay_yaml(
            working_branch=working_branch,
            trigger_branch=trigger_branch,
            coding_agent=coding_agent,
            coding_agent_model=coding_agent_model,
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
            "KANBAN_CODING_AGENT_MODEL": coding_agent_model,
            "KANBAN_POLICY_PROFILE": policy_profile,
        },
    )
    output.append("   OK Saved .env")

    current_turns = _get_max_turns(project_root)
    _, orchestrator_profile, _ = resolve_dispatch_profiles(config)
    if current_turns < max_turns:
        _run([HERMES_BIN, "-p", orchestrator_profile, "config", "set", "agent.max_turns", str(max_turns)])
        output.append(f"   OK max_turns set to {max_turns}")

    skills_src = resolve_plugin_skills_src(DEFAULT_PLUGIN_NAME)
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

    worker_profile, orchestrator_profile = dispatch_profile_names(config)
    reconcile_dispatch_profiles(
        _run,
        HERMES_BIN,
        hermes_home,
        skills_src,
        worker_profile,
        orchestrator_profile,
        force=True,
        log=output.append,
    )

    output.append("OK Settings saved")
    _invalidate_status_cache()
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
        _invalidate_status_cache()
        return {"success": True, "unchanged": True, "output": output}

    try:
        ok, err = _git_sync_to_upstream(install_dir, git_exe, output)
    except Exception as exc:
        logger.exception("plugin update: git sync failed")
        return {"success": False, "error": str(exc), "output": output}

    if not ok:
        return {"success": False, "error": err or "git sync failed", "output": output}

    project_root = resolve_project_root()
    hermes_home = resolve_hermes_home(project_root)
    output.extend(_materialize_plugin_assets(install_dir, hermes_home))

    # Reconcile dispatch profiles so a code pull also fixes profile state:
    # rename legacy worker/orchestrator → kanban-advanced-*, reseed role-only
    # skills, then verify (with one fix retry). Without this, "Update Plugin"
    # pulls new code but leaves stale profiles named worker/orchestrator.
    worker_profile, orchestrator_profile = dispatch_profile_names(
        read_overlay_config(overlay_path(project_root))
    )
    skills_src = install_dir / "plugin" / "skills"
    if skills_src.is_dir():
        reconcile_dispatch_profiles(
            _run,
            HERMES_BIN,
            hermes_home,
            skills_src,
            worker_profile,
            orchestrator_profile,
            force=True,
            log=output.append,
        )

    output.append("OK Plugin updated")
    _invalidate_status_cache()
    return {"success": True, "unchanged": False, "output": output}
