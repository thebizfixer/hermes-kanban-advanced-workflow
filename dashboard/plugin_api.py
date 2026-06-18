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

from fastapi import APIRouter, HTTPException, Request

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
    normalize_notify_lifecycle,
    normalize_notify_deliver,
    normalize_walk_away_mode,
    overlay_path,
    read_overlay_config,
    resolve_branch_settings,
    resolve_coding_agent,
    resolve_coding_agent_model,
    resolve_dispatch_profiles,
    resolve_hermes_home,
    resolve_notify_lifecycle,
    resolve_notify_deliver,
    resolve_walk_away_mode,
    resolve_plugin_install_dir,
    resolve_plugin_skills_src,
    resolve_policy_profile,
    resolve_project_root,
    sync_dispatch_runtime_env,
    sync_project_env,
)
from plugin.coding_agent_env import ensure_coding_agent_runtime_env  # noqa: E402
from plugin.script_materialize import materialize_hermes_scripts  # noqa: E402
from plugin.worktree_provision import ensure_worktreeinclude  # noqa: E402
from plugin.coding_agent import (  # noqa: E402
    CONFLICT_HINT,
    CONFLICT_MESSAGE,
    SMOKE_TIMEOUT_SECONDS,
    check_coding_agent_cli,
    get_available_coding_binaries,
    is_contested_binary_name,
    list_models_for_binary,
    model_display_label,
    normalize_coding_agent_model,
)
from plugin.hermes_model_config import (  # noqa: E402
    apply_model_config_to_profile,
    apply_reasoning_effort_to_profile,
    copy_active_model_to_profile,
    parse_profile_update_payload,
    read_model_config_from_config_show,
    read_reasoning_effort_from_config_show,
    recommended_reasoning_effort_for_profile,
    profile_has_model_config,
    seed_default_reasoning_effort_for_profile,
)
from plugin.file_text import read_utf8_text  # noqa: E402
from plugin.hermes_kanban_bootstrap import apply_hermes_kanban_bootstrap_config  # noqa: E402
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


def _coerce_max_turns(value: object, default: int = 180) -> int:
    """Normalize dashboard max_turns (JSON may send number or string)."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(1, value)
    if isinstance(value, float):
        return max(1, int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return max(1, int(stripped))
    try:
        return max(1, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _dashboard_action_failure(
    output: list[str],
    exc: Exception,
    *,
    action: str,
) -> dict:
    logger.exception("kanban-advanced %s failed", action)
    msg = str(exc).strip() or exc.__class__.__name__
    if not output:
        output.append(f"=== {action} ===")
    output.append(f"   X {msg}")
    return {"success": False, "output": output, "error": msg}


def _run_coding_agent_cli(
    cmd: list[str], timeout: int = SMOKE_TIMEOUT_SECONDS, cwd: str | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Subprocess runner for coding-CLI smoke/list — longer timeout than generic _run."""
    runtime_env = ensure_coding_agent_runtime_env({**os.environ, **(env or {})})
    return _run(cmd, timeout=timeout, cwd=cwd, env=runtime_env)


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


_MODEL_NOT_FOUND_KEYS = (
    "model not found",
    "no such model",
    "unknown model",
    "invalid model",
    "does not exist",
    "not available",
)
_PROVIDER_AUTH_FAILED_KEYS = (
    "authentication",
    "unauthorized",
    "401",
    "403",
    "token",
    "expired",
    "api key",
)


def _check_model_reachable(profile: str) -> tuple[bool | None, str]:
    """Ping the Hermes LLM backend for *profile* via a minimal chat query.

    Returns (True, "") when the model responded, (False, detail) when the ping
    failed with a known cause, or (None, detail) when timed out or ambiguous.
    This checks **Hermes profile provider auth**, not the coding-agent CLI.
    No --yolo flag is needed; "say ok" never triggers tool calls.
    """
    if not profile:
        return None, "missing profile"
    try:
        r = _run([HERMES_BIN, "-p", profile, "chat", "-q", "say ok"], timeout=20)
        out = (r.stdout + r.stderr).lower()
        if r.returncode == 0:
            return True, ""
        if any(k in out for k in _MODEL_NOT_FOUND_KEYS):
            return False, "model not found"
        if any(k in out for k in _PROVIDER_AUTH_FAILED_KEYS):
            return False, "provider auth failed"
        # Non-zero exit with no diagnostic keywords — treat as unknown (yellow).
        return None, "inconclusive"
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except Exception:
        return None, "inconclusive"


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


def _invalidate_profile_probe_cache(profile: str) -> None:
    with _status_cache_lock:
        _status_cache.pop(f"model_reachable:{profile}", None)


def _profile_exists_in_hermes(profile: str, profiles_output: str) -> bool:
    return profile in profiles_output


def _check_profiles(
    project_root: Path | None = None,
    *,
    probe_models: bool = False,
    config_show_cache: dict[str, str] | None = None,
) -> dict:
    result = {}
    config_show_cache = config_show_cache or {}
    if project_root is None:
        project_root = resolve_project_root()
    worker_profile, orchestrator_profile, _ = resolve_dispatch_profiles(
        read_overlay_config(overlay_path(project_root))
    )
    try:
        r = _run([HERMES_BIN, "profile", "list"])
        profiles_output = r.stdout
    except Exception:
        profiles_output = ""

    for profile in _dispatch_profile_list(project_root):
        info: dict = {
            "exists": _profile_exists_in_hermes(profile, profiles_output),
            "has_model": False,
            "model": "",
            "provider": "",
            "model_reachable": None,
            "model_reachability_detail": "",
            "reasoning_effort": "medium",
            "reasoning_effort_configured": False,
            "reasoning_effort_source": "default",
            "recommended_reasoning_effort": recommended_reasoning_effort_for_profile(
                profile,
                orchestrator_profile=orchestrator_profile,
                worker_profile=worker_profile,
            ),
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

            reasoning = read_reasoning_effort_from_config_show(stdout)
            info.update(reasoning)

            if info["has_model"] and probe_models:
                cache_key = f"model_reachable:{profile}"
                cached = _cache_get(cache_key, _TTL_MODEL_PROBE)
                if cached is not None:
                    if isinstance(cached, dict):
                        info["model_reachable"] = cached.get("reachable")
                        info["model_reachability_detail"] = cached.get("detail") or ""
                    else:
                        info["model_reachable"] = cached
                else:
                    reachable, detail = _check_model_reachable(profile)
                    info["model_reachable"] = reachable
                    info["model_reachability_detail"] = detail
                    _cache_set(
                        cache_key,
                        {"reachable": reachable, "detail": detail},
                    )

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
                    read_utf8_text(skill_md), encoding="utf-8"
                )
                count += 1
        lines.append(f"   OK {count} skills -> {skills_dst}")

    lines.extend(
        materialize_hermes_scripts(plugin_root / "scripts", hermes_home / "scripts")
    )
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


def _plugin_git_status_after_update(install_dir: Path, git_exe: str) -> dict:
    """Return up-to-date plugin git fields without fetch — for POST /update response."""
    _cache_set(f"git_behind:{install_dir}", 0)
    hermes_home = resolve_hermes_home()
    local = _git_local_change_count(install_dir, git_exe)
    return {
        "hermes_home": str(hermes_home),
        "plugin_install_path": str(install_dir),
        "plugin_can_update": True,
        "plugin_up_to_date": True,
        "plugin_behind": 0,
        "plugin_update_available": False,
        "plugin_local_changes": local if local is not None else 0,
    }


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
    if is_contested_binary_name(coding_agent):
        coding_agent_cli["conflict"] = CONFLICT_MESSAGE
        coding_agent_cli["conflict_hint"] = CONFLICT_HINT

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
        "available_coding_binaries": get_available_coding_binaries(),
        "policy_profile": resolve_policy_profile(project_root, env=env),
        "notify_lifecycle": resolve_notify_lifecycle(project_root, config=config),
        "notify_deliver": config.get("notify_deliver", ""),
        "notify_deliver_resolved": resolve_notify_deliver(
            project_root, hermes_home=resolve_hermes_home(project_root)
        ),
        "walk_away_mode": resolve_walk_away_mode(
            project_root, config=config, env=env
        ),
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


@router.put("/profiles/{profile_name}")
async def put_profile_settings(profile_name: str, request: Request):
    """PUT /api/plugins/kanban-advanced/profiles/{profile_name}"""
    profile = profile_name.strip()
    if not profile:
        raise HTTPException(status_code=400, detail="profile_name is required")

    project_root = resolve_project_root()
    config = _read_config(project_root)
    worker_profile, orchestrator_profile, _ = resolve_dispatch_profiles(config)
    allowed = {worker_profile, orchestrator_profile}
    if profile not in allowed:
        raise HTTPException(
            status_code=404,
            detail=f"Profile must be a dispatch profile: {', '.join(sorted(allowed))}",
        )

    try:
        r = _run([HERMES_BIN, "profile", "list"])
        profiles_output = r.stdout
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not _profile_exists_in_hermes(profile, profiles_output):
        raise HTTPException(status_code=404, detail=f"Hermes profile not found: {profile}")

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    stdout = _profile_config_show(profile)
    existing_model = read_model_config_from_config_show(stdout)
    try:
        payload = parse_profile_update_payload(body, existing_model=existing_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    hermes_home = resolve_hermes_home(project_root)
    env = _hermes_subprocess_env(hermes_home)

    if payload.get("model"):
        model_cfg = {
            "default": payload["model"],
            "provider": payload.get("provider", ""),
        }
        ok, err = apply_model_config_to_profile(
            _run, HERMES_BIN, profile, model_cfg, env=env
        )
        if not ok:
            raise HTTPException(
                status_code=500,
                detail=err or "Failed to update profile model",
            )

    if payload.get("reasoning_effort"):
        ok, err = apply_reasoning_effort_to_profile(
            _run,
            HERMES_BIN,
            profile,
            payload["reasoning_effort"],
            env=env,
        )
        if not ok:
            raise HTTPException(
                status_code=500,
                detail=err or "Failed to update agent.reasoning_effort",
            )

    _invalidate_profile_probe_cache(profile)

    stdout = _profile_config_show(profile)
    model_cfg = read_model_config_from_config_show(stdout)
    reasoning = read_reasoning_effort_from_config_show(stdout)
    return {
        "ok": True,
        "profile": profile,
        "model": {
            "provider": model_cfg.get("provider", ""),
            "default": model_cfg.get("default", ""),
        },
        "reasoning_effort": reasoning.get("reasoning_effort", "medium"),
        "reasoning_effort_configured": reasoning.get(
            "reasoning_effort_configured", False
        ),
    }


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
    if is_contested_binary_name(binary):
        output.append(f"   !  {CONFLICT_MESSAGE}")
        output.append(f"   !  {CONFLICT_HINT}")
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
    output: list[str] = []
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return _execute_init(body, output)
    except Exception as exc:
        return _dashboard_action_failure(output, exc, action="Bootstrap")


def _execute_init(body: dict, output: list[str]) -> dict:
    project_root = resolve_project_root()
    config_file = overlay_path(project_root)
    existing_config = _read_config(project_root)
    env = _read_env(project_root)
    max_turns = _coerce_max_turns(body.get("max_turns"))

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

    output.append(f"kanban-advanced init -- bootstrapping {project_root}")
    hermes_home_pre = resolve_hermes_home(project_root)
    output.append(f"   HERMES_HOME: {hermes_home_pre}")
    output.append(f"   Working branch: {working_branch}")
    output.append(f"   Trigger branch: {trigger_branch or '(none - optional)'}")
    if "policy_profile" in body:
        policy_profile = normalize_policy_profile(body.get("policy_profile"))
    elif existing_config.get("policy_profile"):
        policy_profile = normalize_policy_profile(existing_config["policy_profile"])
        if existing_config:
            output.append("   Preserved governance profile from existing kanban-config.yaml")
    else:
        policy_profile = resolve_policy_profile(project_root, env=env)
    output.append(f"   Governance profile: {policy_profile}")
    if "notify_lifecycle" in body:
        notify_lifecycle = normalize_notify_lifecycle(body.get("notify_lifecycle"))
    elif "notify_lifecycle" in existing_config:
        notify_lifecycle = normalize_notify_lifecycle(existing_config["notify_lifecycle"])
    else:
        notify_lifecycle = resolve_notify_lifecycle(project_root, env=env)
    output.append(f"   Notifications (lifecycle): {'on' if notify_lifecycle else 'off'}")
    if "walk_away_mode" in body:
        walk_away_mode = normalize_walk_away_mode(body.get("walk_away_mode"))
    elif "notify_on_complete" in body:
        walk_away_mode = normalize_walk_away_mode(body.get("notify_on_complete"))
    elif "walk_away_mode" in existing_config:
        walk_away_mode = normalize_walk_away_mode(existing_config["walk_away_mode"])
    elif "notify_on_complete" in existing_config:
        walk_away_mode = normalize_walk_away_mode(existing_config["notify_on_complete"])
    else:
        walk_away_mode = resolve_walk_away_mode(project_root, env=env)
    output.append(f"   Walk-away mode: {'on' if walk_away_mode else 'off'}")
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

    # Reasoning effort defaults (agent.reasoning_effort) when unset
    for profile in dispatch_profiles:
        seed_default_reasoning_effort_for_profile(
            _run,
            HERMES_BIN,
            profile,
            orchestrator_profile=orchestrator_profile,
            worker_profile=worker_profile,
            env=init_env,
            log=output.append,
        )

    # Max turns
    current_turns = _get_max_turns(project_root)
    if current_turns >= max_turns:
        output.append(f"   OK {orchestrator_profile}: max_turns = {current_turns}")
    else:
        try:
            _run(
                [HERMES_BIN, "-p", orchestrator_profile, "config", "set", "agent.max_turns", str(max_turns)],
                env=init_env,
            )
            output.append(f"   OK max_turns set to {max_turns}")
        except subprocess.TimeoutExpired:
            output.append(
                f"   !  Timed out setting max_turns — run: hermes -p {orchestrator_profile} "
                f"config set agent.max_turns {max_turns}"
            )

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
            notify_lifecycle=notify_lifecycle,
            walk_away_mode=walk_away_mode,
            bundle_path=plugin_root,
            hermes_home=str(hermes_home),
            existing=existing_config,
            project_root=project_root,
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
                (dst_dir / "SKILL.md").write_text(read_utf8_text(skill_md), encoding="utf-8")
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

    output.extend(materialize_hermes_scripts(plugin_root / "scripts", hermes_home / "scripts"))
    output.extend(ensure_worktreeinclude(project_root, hermes_home))

    sync_project_env(
        project_root,
        {
            "HERMES_ENABLE_PROJECT_PLUGINS": "true",
            "KANBAN_CODING_AGENT": coding_agent,
            "KANBAN_CODING_AGENT_MODEL": coding_agent_model,
            "KANBAN_POLICY_PROFILE": policy_profile,
        },
    )
    home_updates = sync_dispatch_runtime_env(project_root)
    if home_updates.get("HOME"):
        output.append(f"   OK HOME={home_updates['HOME']} (coding-agent credentials)")
    else:
        output.append("   !  Could not resolve HOME — set HOME= in .env for gateway workers")
    output.append("   OK")

    # Kanban Hermes config — auto_decompose off + stale dispatch timeout (see dispatch-stale-timeout.md)
    apply_hermes_kanban_bootstrap_config(_run, HERMES_BIN, log=output.append)

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
    output: list[str] = []
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return _execute_save(body, output)
    except Exception as exc:
        return _dashboard_action_failure(output, exc, action="Saving settings")


def _execute_save(body: dict, output: list[str]) -> dict:
    project_root = resolve_project_root()
    config = _read_config(project_root)
    config_file = overlay_path(project_root)
    if not config_file.is_file():
        return {
            "success": False,
            "error": "Config file not found. Run bootstrap first.",
        }

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
    if "notify_lifecycle" in body:
        notify_lifecycle = normalize_notify_lifecycle(body.get("notify_lifecycle"))
    else:
        notify_lifecycle = resolve_notify_lifecycle(project_root, config=config)
    merged_config = dict(config)
    if "notify_deliver" in body:
        deliver_override = normalize_notify_deliver(body.get("notify_deliver"))
        if deliver_override:
            merged_config["notify_deliver"] = deliver_override
        else:
            merged_config.pop("notify_deliver", None)
    max_turns = _coerce_max_turns(body.get("max_turns"))

    output.append("=== Saving settings ===")
    output.append(f"   Working branch: {working_branch}")
    output.append(f"   Trigger branch: {trigger_branch or '(none - optional)'}")
    output.append(f"   Governance profile: {policy_profile}")
    output.append(f"   Notifications (lifecycle): {'on' if notify_lifecycle else 'off'}")
    deliver_resolved = resolve_notify_deliver(
        project_root, hermes_home=resolve_hermes_home(project_root)
    )
    if merged_config.get("notify_deliver"):
        output.append(
            f"   Lifecycle deliver: {merged_config['notify_deliver']} (resolved: {deliver_resolved})"
        )
    else:
        output.append(f"   Lifecycle deliver: auto ({deliver_resolved})")
    if "walk_away_mode" in body:
        walk_away_mode = normalize_walk_away_mode(body.get("walk_away_mode"))
    elif "notify_on_complete" in body:
        walk_away_mode = normalize_walk_away_mode(body.get("notify_on_complete"))
    else:
        walk_away_mode = resolve_walk_away_mode(project_root, config=config, env=env)
    output.append(f"   Walk-away mode: {'on' if walk_away_mode else 'off'}")
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
            notify_lifecycle=notify_lifecycle,
            walk_away_mode=walk_away_mode,
            bundle_path=plugin_root,
            hermes_home=str(hermes_home),
            existing=merged_config,
            project_root=project_root,
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
    home_updates = sync_dispatch_runtime_env(project_root)
    if home_updates.get("HOME"):
        output.append(f"   OK HOME={home_updates['HOME']} (coding-agent credentials)")
    else:
        output.append("   !  Could not resolve HOME — set HOME= in .env for gateway workers")
    output.append("   OK Saved .env")

    current_turns = _get_max_turns(project_root)
    _, orchestrator_profile, _ = resolve_dispatch_profiles(config)
    if current_turns < max_turns:
        try:
            _run(
                [HERMES_BIN, "-p", orchestrator_profile, "config", "set", "agent.max_turns", str(max_turns)],
                env=_hermes_subprocess_env(hermes_home),
            )
            output.append(f"   OK max_turns set to {max_turns}")
        except subprocess.TimeoutExpired:
            output.append(
                f"   !  Timed out setting max_turns — run: hermes -p {orchestrator_profile} "
                f"config set agent.max_turns {max_turns}"
            )

    skills_src = resolve_plugin_skills_src(DEFAULT_PLUGIN_NAME)
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    count = 0
    if skills_src.is_dir():
        for child in sorted(skills_src.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = skills_dst / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(read_utf8_text(skill_md), encoding="utf-8")
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
        return {
            "success": True,
            "unchanged": True,
            "output": output,
            **_plugin_git_status_after_update(install_dir, git_exe),
        }

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
    output.extend(ensure_worktreeinclude(project_root, hermes_home))

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
    return {
        "success": True,
        "unchanged": False,
        "output": output,
        **_plugin_git_status_after_update(install_dir, git_exe),
    }
