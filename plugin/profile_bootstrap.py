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
    DEFAULT_CODER_PROFILE,
    DEFAULT_ORCHESTRATOR_PROFILE,
    DEFAULT_WORKER_PROFILE,
    LEGACY_ORCHESTRATOR_PROFILE,
    LEGACY_WORKER_PROFILE,
    PLUGIN_ROOT,
    PROFILE_SKILL_SETS_BY_ROLE,
    resolve_dispatch_profiles,
    resolve_hermes_home,
)
from .file_text import read_utf8_text

_DATA_REFERENCES = PLUGIN_ROOT / "plugin" / "data" / "references"

RunFn = Callable[..., subprocess.CompletedProcess]

DISPATCH_PROFILE_SPECS: tuple[tuple[str, str], ...] = (
    (DEFAULT_WORKER_PROFILE, LEGACY_WORKER_PROFILE),
    (DEFAULT_ORCHESTRATOR_PROFILE, LEGACY_ORCHESTRATOR_PROFILE),
    (DEFAULT_CODER_PROFILE, None),
)

NO_BUNDLED_SKILLS_MARKER = ".no-bundled-skills"
NO_BUNDLED_SKILLS_TEXT = (
    "This profile opted out of bundled-skill seeding "
    "(kanban-advanced dispatch profile).\n"
    "Delete this file to re-enable sync on the next `hermes update`.\n"
)

# Files safe to copy from the default profile when bootstrapping dispatch profiles.
# .env is included because Hermes profiles do NOT inherit env vars from the
# main $HERMES_HOME/.env — each profile needs its own copy. The reconciliation
# step re-syncs .env and auth.json on every bootstrap (not just at creation),
# so operator key updates propagate to dispatch profiles on Update Plugin / re-init.
# config.yaml is NOT synced — each profile manages its own model/max_turns config
# through the dashboard or hermes config set.
_PROFILE_CONFIG_FILES = (".env", "auth.json")

# plugin/data/prompts/*.md → profiles/<name>/SOUL.md
_PROFILE_SOUL_PROMPTS_BY_ROLE: dict[str, str] = {
    "worker": "worker.md",
    "orchestrator": "orchestrator.md",
}


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


def _profile_home(hermes_home: Path, profile: str) -> Path:
    return hermes_home / "profiles" / profile


def _resolve_profile_home_cli(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    env: dict[str, str] | None,
) -> Path | None:
    """Ask Hermes where a profile actually lives (authoritative vs guessed paths)."""
    try:
        r = _run_home(run, [hermes_bin, "profile", "show", profile], env)
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            if line.strip().lower().startswith("path:"):
                raw = line.split(":", 1)[1].strip()
                if raw:
                    return Path(raw).expanduser().resolve()
    except Exception:
        return None
    return None


def _resolve_profile_home(
    run: RunFn,
    hermes_bin: str,
    hermes_home: Path,
    profile: str,
    env: dict[str, str] | None,
) -> Path | None:
    cli_home = _resolve_profile_home_cli(run, hermes_bin, profile, env)
    if cli_home is not None:
        return cli_home
    fallback = _profile_home(hermes_home, profile)
    return fallback if fallback.is_dir() else None


def _default_profile_home(hermes_home: Path) -> Path:
    """Hermes stores the active default profile at $HERMES_HOME root."""
    for candidate in (hermes_home, hermes_home / "profiles" / "default"):
        if (candidate / "config.yaml").is_file() or (candidate / "SOUL.md").is_file():
            return candidate
    return hermes_home


def _opt_out_bundled_skills(profile_home: Path) -> None:
    """Prevent `hermes update` from re-seeding Hermes bundled skills into this profile."""
    marker = profile_home / NO_BUNDLED_SKILLS_MARKER
    if not marker.is_file():
        marker.write_text(NO_BUNDLED_SKILLS_TEXT, encoding="utf-8")


def materialize_skill_dir(
    src_skill_dir: Path,
    dst_skill_dir: Path,
    *,
    bundle_data_references: Path | None = None,
) -> None:
    """Copy SKILL.md and optional references/ for skill_view(name, file_path) resolution.

    When ``bundle_data_references`` is set (kanban-advanced bridge skill), also copy
    ``plugin/data/references/*.md`` into ``references/`` so supervisors can load shared
    docs via ``skill_view("kanban-advanced:kanban-advanced", "references/<file>.md")``.
    Skips ``in-flight-governance-index.md`` from the bundle when the skill-local SSOT
    copy already exists.
    """
    skill_md = src_skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(skill_md)
    dst_skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_md, dst_skill_dir / "SKILL.md")
    refs_src = src_skill_dir / "references"
    refs_dst = dst_skill_dir / "references"
    if refs_src.is_dir():
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        shutil.copytree(refs_src, refs_dst)
    if bundle_data_references and bundle_data_references.is_dir():
        refs_dst.mkdir(parents=True, exist_ok=True)
        for ref in bundle_data_references.glob("*.md"):
            if ref.name == "in-flight-governance-index.md" and (refs_dst / ref.name).is_file():
                continue
            shutil.copy2(ref, refs_dst / ref.name)


def _copy_profile_config_from_default(hermes_home: Path, profile: str) -> None:
    """Copy model/auth config only — never skills or SOUL (role prompts are separate)."""
    src = _default_profile_home(hermes_home)
    dst = _profile_home(hermes_home, profile)
    dst.mkdir(parents=True, exist_ok=True)
    for name in _PROFILE_CONFIG_FILES:
        src_file = src / name
        if src_file.is_file():
            shutil.copy2(src_file, dst / name)


def _create_dispatch_profile(
    run: RunFn,
    hermes_bin: str,
    env: dict[str, str] | None,
    hermes_home: Path,
    profile_name: str,
) -> subprocess.CompletedProcess:
    """Create a dispatch profile without inheriting default bundled skills."""
    r = _run_home(
        run, [hermes_bin, "profile", "create", profile_name, "--no-skills"], env
    )
    if r.returncode == 0:
        profile_home = _resolve_profile_home_cli(run, hermes_bin, profile_name, env)
        if profile_home is None:
            profile_home = _profile_home(hermes_home, profile_name)
        _opt_out_bundled_skills(profile_home)
        _copy_profile_config_from_default(hermes_home, profile_name)
        # Hermes may leave an empty skills/ dir; remove before role-only seeding.
        skills_dir = profile_home / "skills"
        if skills_dir.exists():
            shutil.rmtree(skills_dir, ignore_errors=True)
    return r


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
    home = Path(hermes_home).expanduser().resolve() if hermes_home else resolve_hermes_home()
    env = _home_env(home)
    profiles_output = _profiles_list_text(run, hermes_bin, env)

    for new_name, legacy_name in DISPATCH_PROFILE_SPECS:
        if _profile_present(profiles_output, new_name):
            log(f"   OK {new_name}")
            continue

        if legacy_name and _profile_present(profiles_output, legacy_name):
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
                    renamed_home = (
                        _resolve_profile_home_cli(run, hermes_bin, new_name, env)
                        or _profile_home(home, new_name)
                    )
                    _opt_out_bundled_skills(renamed_home)
                    skills_dir = renamed_home / "skills"
                    if skills_dir.exists():
                        shutil.rmtree(skills_dir, ignore_errors=True)
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
            r = _create_dispatch_profile(run, hermes_bin, env, home, new_name)
            if r.returncode == 0:
                log(f"   OK Created '{new_name}' (no default skills)")
                profiles_output += f"\n{new_name}"
            else:
                log(f"   X Failed to create '{new_name}': {r.stderr.strip()}")
                return None
        else:
            log(
                f"   X Profile '{new_name}' is required. "
                f"Run: hermes kanban-advanced init"
            )
            return None

    return DEFAULT_WORKER_PROFILE, DEFAULT_ORCHESTRATOR_PROFILE


def _prompts_src_from_skills(skills_src: Path) -> Path:
    return skills_src.parent / "data" / "prompts"


def seed_dispatch_profile_souls(
    run: RunFn,
    hermes_bin: str,
    hermes_home: Path,
    prompts_src: Path,
    worker_profile: str,
    orchestrator_profile: str,
    *,
    env: dict[str, str] | None = None,
    log: Callable[[str], Any] = print,
) -> int:
    """Install plugin role prompts as each dispatch profile's SOUL.md."""
    role_profiles = {
        "worker": worker_profile,
        "orchestrator": orchestrator_profile,
    }
    seeded = 0
    for role, profile in role_profiles.items():
        prompt_name = _PROFILE_SOUL_PROMPTS_BY_ROLE[role]
        prompt_file = prompts_src / prompt_name
        profile_home = _resolve_profile_home(run, hermes_bin, hermes_home, profile, env)
        if profile_home is None or not profile_home.is_dir():
            log(f"   !  {profile}: profile home not found — skipping SOUL.md")
            continue
        if not prompt_file.is_file():
            log(f"   !  {profile}: prompt missing at {prompt_file} — skipping SOUL.md")
            continue
        soul_dst = profile_home / "SOUL.md"
        soul_dst.write_text(read_utf8_text(prompt_file), encoding="utf-8")
        log(f"   OK {profile}: SOUL.md <- {prompt_name} ({profile_home})")
        seeded += 1
    return seeded


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
    run: RunFn,
    hermes_bin: str,
    hermes_home: Path,
    skills_src: Path,
    worker_profile: str,
    orchestrator_profile: str,
    *,
    env: dict[str, str] | None = None,
    log: Callable[[str], Any] = print,
) -> int:
    """Wipe inherited profile skills and seed only role-specific plugin skills."""
    profile_map = {
        worker_profile: PROFILE_SKILL_SETS_BY_ROLE["worker"],
        orchestrator_profile: PROFILE_SKILL_SETS_BY_ROLE["orchestrator"],
    }
    # Add coder profile to the map if it exists
    if "coder" in PROFILE_SKILL_SETS_BY_ROLE:
        coder_name = "kanban-advanced-coder"
        coder_home = _profile_home(hermes_home, coder_name)
        if coder_home.is_dir():
            profile_map[coder_name] = PROFILE_SKILL_SETS_BY_ROLE["coder"]
    total = 0
    for profile, allowed_skills in profile_map.items():
        profile_home = _resolve_profile_home(run, hermes_bin, hermes_home, profile, env)
        if profile_home is None or not profile_home.is_dir():
            guessed = _profile_home(hermes_home, profile)
            log(f"   !  {profile}: profile home not found (guessed {guessed}) — skipping")
            continue
        _opt_out_bundled_skills(profile_home)
        profile_skills = profile_home / "skills"
        if profile_skills.exists():
            shutil.rmtree(profile_skills, ignore_errors=True)
        seeded = 0
        for child in sorted(skills_src.iterdir()):
            if child.name not in allowed_skills:
                continue
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                bundle = _DATA_REFERENCES if child.name == "kanban-advanced" else None
                materialize_skill_dir(
                    child,
                    profile_skills / child.name,
                    bundle_data_references=bundle,
                )
                seeded += 1
        log(f"   OK {profile}: {seeded} skills seeded {sorted(allowed_skills)} ({profile_home})")
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
        profile_home = _resolve_profile_home(run, hermes_bin, hermes_home, profile, env)
        if profile_home is None:
            issues.append(f"profile '{profile}' home path could not be resolved")
            continue
        if not (profile_home / NO_BUNDLED_SKILLS_MARKER).is_file():
            issues.append(
                f"profile '{profile}' missing {NO_BUNDLED_SKILLS_MARKER} "
                "(Hermes may re-sync bundled default skills)"
            )
        if not (profile_home / "SOUL.md").is_file():
            issues.append(f"profile '{profile}' missing SOUL.md")
        skills_dir = profile_home / "skills"
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

    # Sync config.yaml, .env, and auth.json from the default profile on every
    # bootstrap. Hermes profiles do NOT inherit env vars — each profile needs
    # its own .env with current API keys. This ensures operator key updates
    # propagate to dispatch profiles on Update Plugin / re-init.
    for profile_name in (worker_profile, orchestrator_profile):
        _copy_profile_config_from_default(hermes_home, profile_name)
    # Also sync coder profile if it exists
    coder_profile = "kanban-advanced-coder"
    coder_home = _profile_home(hermes_home, coder_profile)
    if coder_home.is_dir():
        _copy_profile_config_from_default(hermes_home, coder_profile)
    log("   OK Synced config.yaml + .env + auth.json from default profile")

    env = _home_env(hermes_home)
    prompts_src = _prompts_src_from_skills(skills_src)
    if not prompts_src.is_dir():
        log(f"   !  Prompts dir missing at {prompts_src}")
    seed_dispatch_profile_souls(
        run,
        hermes_bin,
        hermes_home,
        prompts_src,
        worker_profile,
        orchestrator_profile,
        env=env,
        log=log,
    )
    # Also seed coder SOUL if profile exists
    if coder_home.is_dir() and prompts_src.is_dir():
        seed_dispatch_profile_souls(
            run, hermes_bin, hermes_home, prompts_src,
            coder_profile, env=env, log=log,
        )
    seed_dispatch_profile_skills(
        run,
        hermes_bin,
        hermes_home,
        skills_src,
        worker_profile,
        orchestrator_profile,
        env=env,
        log=log,
    )
    # Also seed coder skills if profile exists
    if coder_home.is_dir():
        seed_dispatch_profile_skills(
            run, hermes_bin, hermes_home, skills_src,
            coder_profile, coder_profile, env=env, log=log,
        )

    issues = verify_dispatch_profiles(
        run, hermes_bin, hermes_home, worker_profile, orchestrator_profile
    )
    if issues:
        log("   !  Profile verification failed — applying fix:")
        for issue in issues:
            log(f"      - {issue}")
        # One reseed attempt covers stale/extra skill dirs after rename.
        seed_dispatch_profile_souls(
            run,
            hermes_bin,
            hermes_home,
            prompts_src,
            worker_profile,
            orchestrator_profile,
            env=env,
            log=log,
        )
        seed_dispatch_profile_skills(
            run,
            hermes_bin,
            hermes_home,
            skills_src,
            worker_profile,
            orchestrator_profile,
            env=env,
            log=log,
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
