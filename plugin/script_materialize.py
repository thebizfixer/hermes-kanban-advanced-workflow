"""Copy kanban cron/invoke scripts into $HERMES_HOME/scripts."""

from __future__ import annotations

from pathlib import Path

HERMES_SCRIPT_NAMES = (
    "auto_unblock.sh",
    "board_keeper.sh",
    "kanban_lifecycle_notify.sh",
    "kanban_completion_notify.sh",
    "kanban_walk_away_post_exec.sh",
    "kanban_intervention_inc.sh",
    "kanban_git_ops.sh",
    "token_tracker.py",
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
)


def materialize_hermes_scripts(scripts_src: Path, scripts_dst: Path) -> list[str]:
    """Copy top-level scripts and scripts/lib helpers into HERMES_HOME."""
    lines: list[str] = []
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in HERMES_SCRIPT_NAMES:
        src = scripts_src / script_name
        dst = scripts_dst / script_name
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                dst.chmod(0o755)
                lines.append(f"   OK lib/{name} -> {dst}")
        for name in LIB_PYTHON_NAMES:
            src = lib_src / name
            if src.exists():
                dst = lib_dst / name
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                lines.append(f"   OK lib/{name} -> {dst}")
    return lines
