"""Copy kanban cron/invoke scripts into $HERMES_HOME; preserve operator-edited skills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from plugin.file_text import read_utf8_text

MANIFEST_FILENAME = ".materialize-manifest.json"

HERMES_SCRIPT_NAMES = (
    "auto_unblock.sh",
    "board_keeper.sh",
    "kanban_lifecycle_notify.sh",
    "kanban_completion_notify.sh",
    "kanban_walk_away_post_exec.sh",
    "kanban_intervention_inc.sh",
    "kanban_git_ops.sh",
    "token_tracker.py",
    "log_invoke_tokens.py",
    "hermes_token_meter.py",
    "coding_agent_invoke.sh",
    "worktree_setup.sh",
    "install_pre_push_hook.sh",
    "install_pre_commit_hook.sh",
)

LIB_SCRIPT_NAMES = (
    "coding_agent_env.sh",
    "coding_agent_auth_lock.sh",
    "kanban_config.sh",
    "kanban_bundle.sh",
    "worktree_include.sh",
    "plan_paths.sh",
    "kanban_cli_parse.sh",
    "kanban_logs.sh",
    "gateway_hermes_home.sh",
    "auto_unblock_core.sh",
    "preflight_cache.sh",
    "resolve_notify_deliver.sh",
    "governance_profile.sh",
    "bash_counters.sh",
)

LIB_PYTHON_NAMES = (
    "plan_paths.py",
    "plan_parse.py",
    "cli_output_parse.py",
    "governance_profile.py",
    "decompose_stamp.py",
    "cross_plan_memory.py",
    "token_tracker_import.py",
    "hermes_notify_deliver.py",
    "card_body.py",
    "presentation_acceptance.py",
    "verify_optimization_presentation.py",
    "orchestrator_token_checkpoint.py",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def manifest_path(skills_dst: Path) -> Path:
    return skills_dst / MANIFEST_FILENAME


def load_skill_manifest(skills_dst: Path) -> dict[str, str]:
    path = manifest_path(skills_dst)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return {}


def save_skill_manifest(skills_dst: Path, manifest: dict[str, str]) -> None:
    skills_dst.mkdir(parents=True, exist_ok=True)
    manifest_path(skills_dst).write_text(
        json.dumps(dict(sorted(manifest.items())), indent=2) + "\n",
        encoding="utf-8",
    )


def _rel_skill_key(dst_root: Path, file_path: Path) -> str:
    return file_path.relative_to(dst_root).as_posix()


def materialize_skills_with_preservation(
    skills_src: Path,
    skills_dst: Path,
    *,
    materialize_skill_dir: Callable[..., None],
    bundle_data_references: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[int, list[str]]:
    """Materialize plugin skills; preserve files the operator edited since last ship."""
    emit = log or (lambda _msg: None)
    manifest = load_skill_manifest(skills_dst)
    warnings: list[str] = []
    count = 0
    new_manifest: dict[str, str] = dict(manifest)
    preserved_bytes: dict[str, bytes] = {}

    if not skills_src.is_dir():
        return 0, warnings

    if skills_dst.is_dir():
        for dst_file in skills_dst.rglob("*"):
            if not dst_file.is_file() or dst_file.name == MANIFEST_FILENAME:
                continue
            if dst_file.name.startswith(".preserve-"):
                continue
            key = _rel_skill_key(skills_dst, dst_file)
            src_file = skills_src / key
            if not src_file.is_file():
                continue
            dst_hash = sha256_file(dst_file)
            src_hash = sha256_file(src_file)
            shipped_hash = manifest.get(key, "")
            if dst_hash != src_hash and dst_hash != shipped_hash:
                preserved_bytes[key] = dst_file.read_bytes()
                msg = f"   !  Preserving operator-edited skill file (skipped overwrite): {key}"
                warnings.append(msg)
                emit(msg)

    for child in sorted(skills_src.iterdir()):
        skill_md = child / "SKILL.md"
        if not (child.is_dir() and skill_md.is_file()):
            continue
        dst_dir = skills_dst / child.name
        bundle = bundle_data_references if child.name == "kanban-advanced" else None
        materialize_skill_dir(child, dst_dir, bundle_data_references=bundle)
        count += 1

    for key, content in preserved_bytes.items():
        target = skills_dst / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    for src_file in skills_src.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(skills_src)
        key = rel.as_posix()
        dst_file = skills_dst / rel
        if key in preserved_bytes and dst_file.is_file():
            new_manifest[key] = sha256_file(dst_file)
        else:
            new_manifest[key] = sha256_file(src_file)

    save_skill_manifest(skills_dst, new_manifest)
    return count, warnings


def materialize_hermes_scripts(scripts_src: Path, scripts_dst: Path) -> list[str]:
    """Copy top-level scripts and scripts/lib helpers into HERMES_HOME."""
    lines: list[str] = []
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in HERMES_SCRIPT_NAMES:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(read_utf8_text(src), encoding="utf-8")
            dst.chmod(0o755)
            lines.append(f"   OK {script_name} -> {dst}")
    lib_src = scripts_src / "lib"
    lib_dst = scripts_dst / "lib"
    if lib_src.is_dir():
        lib_dst.mkdir(parents=True, exist_ok=True)
        for name in LIB_SCRIPT_NAMES:
            src = lib_src / name
            if src.exists():
                dst = lib_dst / name
                dst.write_text(read_utf8_text(src), encoding="utf-8")
                dst.chmod(0o755)
                lines.append(f"   OK lib/{name} -> {dst}")
        for name in LIB_PYTHON_NAMES:
            src = lib_src / name
            if src.exists():
                dst = lib_dst / name
                dst.write_text(read_utf8_text(src), encoding="utf-8")
                lines.append(f"   OK lib/{name} -> {dst}")
    return lines
