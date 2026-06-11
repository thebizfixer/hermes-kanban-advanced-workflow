"""Dispatch profile ensure, skill isolation, verification, and seeding.

All hermes profile subprocess calls target an explicit HERMES_HOME so the
rename/create/verify operations always hit the same state directory that
hosts the dispatch profiles (project plugins resolve a project-local
HERMES_HOME, not the global ~/.hermes).
"""

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


def _home_env(hermes_home: Path | str | None) -> dict[str, str] | None:
    """Build a subprocess env that pins HERMES_HOME, or None to inherit."""
    if hermes_home is None:
        return None
    return {**os.environ, "HERMES_HOME": str(hermes_home)}


def _run_home(
    run: RunFn, cmd: list[str], env: dict[str, str] | None
) -> subprocess.CompletedProcess:
    """Call the injected run fn, passing env only when set (back-compat)."""
    if env is None:
        return run(cmd)
    try:
        return run(cmd, env=env)
    except TypeError:
        # Injected run fn predates the env kwarg — fall back to process env.
        prev = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = env["HERMES_HOME"]
        try:
            return run(cmd)
        finally:
            if prev is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = prev


def _profiles_list_text(
    run: RunFn, hermes_bin: str, env: dict[str, str] | None
) -> str:
    try:
        return _run_home(run, [hermes_bin, "profile", "list"], env).stdout
    except Exception:
        return ""


def _profile_present(profiles_output: str, name: str) -> bool:
    """Whole-token match so 'worker' does not match 'kanban-advanced-worker'."""
    import re

    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", profiles_output) is not None


def ensure_dispatch_profiles(
    run: RunFn,
    hermes_bin: str,
    *,
    hermes_home: Path | str | None = None,
    force: bool = False,
    prompt_yes_no: Callable[[str], bool] | None = None,
    log: Callable[[str], Any] = print,
) -> tuple[str, str] | None:
    """Ensure dispatch profiles exist; rename legacy short names when present."""
    env = _home_env(hermes_home)
    profiles_output = _profiles_list_text(run, hermes_bin, env)

    for new_name, legacy_name in DISPATCH_PROFILE_SPECS:
        if _profile_present(profiles_output, new_name):
            log(f"   OK {new_name}")
            continue

        if _profile_present(profiles_output, legacy_name):
            should_rename = force or (prompt_yes_no and prompt_yes_no(
                f"   Rename legacy profile '{legacy_name}' -> '{new_name}'?"
            ))
            if should_rename:
                r = _run_home(
                    run, [hermes_bin, "profile", "rename", legacy_name, new_name], env
                )
                if r.returncode == 0:
                    log(f"   OK Renamed '{legacy_name}' -> '{new_name}'")
                    profiles_output += f"\n{new_name}"
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
            r = _run_home(
                run, [hermes_bin, "profile", "create", new_name, "--clone"], env
            )
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


def verify_dispatch_profiles(
    run: RunFn,
    hermes_bin: str,
    hermes_home: Path,
    worker_profile: str,
    orchestrator_profile: str,
) -> list[str]:
    """Return a list of problems; empty means profiles are correctly named + isolated.

    Checks, per role profile:
      * the profile exists in `hermes profile list` (correct prefixed name)
      * its skills/ dir contains EXACTLY the role's allowed skill set
    """
    env = _home_env(hermes_home)
    profiles_output = _profiles_list_text(run, hermes_bin, env)
    issues: list[str] = []

    role_map = {
        worker_profile: PROFILE_SKILL_SETS_BY_ROLE["worker"],
        orchestrator_profile: PROFILE_SKILL_SETS_BY_ROLE["orchestrator"],
    }
    for profile, allowed in role_map.items():
        if not _profile_present(profiles_output, profile):
            issues.append(f"profile '{profile}' not found (expected prefixed name)")
        skills_dir = hermes_home / "profiles" / profile / "skills"
        if not skills_dir.is_dir():
            issues.append(f"profile '{profile}' has no skills dir")
            continue
        present = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = allowed - present
        extra = present - allowed
        for name in sorted(missing):
            issues.append(f"profile '{profile}' missing skill '{name}'")
        for name in sorted(extra):
            issues.append(f"profile '{profile}' has unexpected skill '{name}'")
    return issues


def reconcile_dispatch_profiles(
    run: RunFn,
    hermes_bin: str,
    hermes_home: Path,
    skills_src: Path,
    worker_profile: str,
    orchestrator_profile: str,
    *,
    force: bool = True,
    prompt_yes_no: Callable[[str], bool] | None = None,
    log: Callable[[str], Any] = print,
) -> bool:
    """Ensure + seed + verify (with one fix retry). Returns True when verified clean.

    This is the single entry point init/update should call so the end state is
    always: prefixed profile names, role-only skills, confirmed by verification.
    """
    if not ensure_dispatch_profiles(
        run,
        hermes_bin,
        hermes_home=hermes_home,
        force=force,
        prompt_yes_no=prompt_yes_no,
        log=log,
    ):
        return False

    seed_dispatch_profile_skills(
        hermes_home, skills_src, worker_profile, orchestrator_profile, log=log
    )

    issues = verify_dispatch_profiles(
        run, hermes_bin, hermes_home, worker_profile, orchestrator_profile
    )
    if issues:
        log("   !  Profile verification failed — applying fix:")
        for issue in issues:
            log(f"      - {issue}")
        # One reseed attempt covers stale/extra skill dirs after rename.
        seed_dispatch_profile_skills(
            hermes_home, skills_src, worker_profile, orchestrator_profile, log=log
        )
        issues = verify_dispatch_profiles(
            run, hermes_bin, hermes_home, worker_profile, orchestrator_profile
        )

    if issues:
        log("   X Profile verification STILL failing after fix:")
        for issue in issues:
            log(f"      - {issue}")
        return False

    log(f"   OK Profiles verified: {worker_profile}, {orchestrator_profile} (role skills only)")
    return True


def dispatch_profile_names(existing: dict[str, str] | None = None) -> tuple[str, str]:
    """Canonical worker and orchestrator profile names for this project."""
    worker, orchestrator, _ = resolve_dispatch_profiles(existing)
    return worker, orchestrator
