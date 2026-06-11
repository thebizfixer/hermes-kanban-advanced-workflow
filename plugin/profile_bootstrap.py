"""Dispatch profile ensure, skill isolation check, and plugin skill seeding."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config_overlay import (
    DEFAULT_ORCHESTRATOR_PROFILE,
    DEFAULT_WORKER_PROFILE,
    LEGACY_ORCHESTRATOR_PROFILE,
    LEGACY_WORKER_PROFILE,
    PROFILE_SKILL_SETS_BY_ROLE,
    resolve_dispatch_profiles,
)

RunFn = Callable[..., subprocess.CompletedProcess]

DISPATCH_PROFILE_SPECS: tuple[tuple[str, str], ...] = (
    (DEFAULT_WORKER_PROFILE, LEGACY_WORKER_PROFILE),
    (DEFAULT_ORCHESTRATOR_PROFILE, LEGACY_ORCHESTRATOR_PROFILE),
)


def _profiles_list_text(run: RunFn, hermes_bin: str) -> str:
    try:
        return run([hermes_bin, "profile", "list"]).stdout
    except Exception:
        return ""


def ensure_dispatch_profiles(
    run: RunFn,
    hermes_bin: str,
    *,
    force: bool = False,
    prompt_yes_no: Callable[[str], bool] | None = None,
    log: Callable[[str], Any] = print,
) -> tuple[str, str] | None:
    """Ensure dispatch profiles exist; rename legacy short names when present."""
    profiles_output = _profiles_list_text(run, hermes_bin)

    for new_name, legacy_name in DISPATCH_PROFILE_SPECS:
        if new_name in profiles_output:
            log(f"   OK {new_name}")
            continue

        if legacy_name in profiles_output:
            should_rename = force or (prompt_yes_no and prompt_yes_no(
                f"   Rename legacy profile '{legacy_name}' → '{new_name}'?"
            ))
            if should_rename:
                r = run([hermes_bin, "profile", "rename", legacy_name, new_name])
                if r.returncode == 0:
                    log(f"   OK Renamed '{legacy_name}' → '{new_name}'")
                    profiles_output = profiles_output.replace(legacy_name, new_name)
                else:
                    log(f"   X Failed to rename '{legacy_name}': {r.stderr.strip()}")
                    return None
            else:
                log(
                    f"   X Profile '{new_name}' is required. "
                    f"Rename legacy profile: hermes profile rename {legacy_name} {new_name}"
                )
                return None
            continue

        should_create = force or (prompt_yes_no and prompt_yes_no(
            f"   Profile '{new_name}' not found. Create it now?"
        ))
        if should_create:
            r = run([hermes_bin, "profile", "create", new_name, "--clone"])
            if r.returncode == 0:
                log(f"   OK Created '{new_name}'")
                profiles_output += f"\n{new_name}"
            else:
                log(f"   X Failed to create '{new_name}': {r.stderr.strip()}")
                return None
        else:
            log(
                f"   X Profile '{new_name}' is required. "
                f"Run: hermes profile create {new_name} --clone"
            )
            return None

    return DEFAULT_WORKER_PROFILE, DEFAULT_ORCHESTRATOR_PROFILE


def run_provision_profile_check(
    project_root: Path,
    scripts_dir: Path,
    run: RunFn,
) -> subprocess.CompletedProcess | None:
    """Run provision.sh --profiles-only --check. Returns None when bash is unavailable."""
    bash = shutil.which("bash")
    if not bash:
        return None
    script = scripts_dir / "provision.sh"
    if not script.is_file():
        return None
    return run(
        [bash, str(script), "--profiles-only", "--check"],
        cwd=str(project_root),
        timeout=120,
    )


def seed_dispatch_profile_skills(
    hermes_home: Path,
    skills_src: Path,
    worker_profile: str,
    orchestrator_profile: str,
    *,
    log: Callable[[str], Any] = print,
) -> int:
    """Wipe inherited profile skills and seed only role-specific plugin skills."""
    profile_map = {
        worker_profile: PROFILE_SKILL_SETS_BY_ROLE["worker"],
        orchestrator_profile: PROFILE_SKILL_SETS_BY_ROLE["orchestrator"],
    }
    total = 0
    for profile, allowed_skills in profile_map.items():
        profile_home = hermes_home / "profiles" / profile
        if not profile_home.is_dir():
            log(f"   !  {profile}: profile home not found at {profile_home} — skipping")
            continue
        profile_skills = profile_home / "skills"
        if profile_skills.exists():
            shutil.rmtree(profile_skills, ignore_errors=True)
        seeded = 0
        for child in sorted(skills_src.iterdir()):
            if child.name not in allowed_skills:
                continue
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                dst_dir = profile_skills / child.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "SKILL.md").write_text(
                    skill_md.read_text(encoding="utf-8"), encoding="utf-8"
                )
                seeded += 1
        log(f"   OK {profile}: {seeded} skills seeded {sorted(allowed_skills)}")
        total += seeded
    return total


def dispatch_profile_names(existing: dict[str, str] | None = None) -> tuple[str, str]:
    """Canonical worker and orchestrator profile names for this project."""
    worker, orchestrator, _ = resolve_dispatch_profiles(existing)
    return worker, orchestrator
