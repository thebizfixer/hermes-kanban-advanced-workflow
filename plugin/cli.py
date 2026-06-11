"""CLI subcommands — `hermes kanban-advanced <subcommand>`.

Naming: The plugin is named 'kanban-advanced' (plugin.yaml: name), so the
register_cli_command prefix is 'hermes kanban-advanced'. We use subcommand group
name 'kanban-advanced' to match. This avoids collision with the built-in
'hermes kanban' command group (which already has decompose, list, show, etc.).

Subcommands:
    decompose       Governed card creation from a plan
    list            Board status (delegates to hermes kanban list)
    show            Card details (delegates to hermes kanban show)
    validate        Pre-dispatch board validation
    verify-optimization  Plan optimization gate check
    preflight       Pre-decomposition environment gate
    init            Post-install bootstrap for a project
"""

import argparse
import logging
import re
import subprocess
import sys
import os
from pathlib import Path

from .config_overlay import (
    DEFAULT_ORCHESTRATOR_PROFILE,
    DEFAULT_WORKER_PROFILE,
    build_overlay_yaml,
    normalize_policy_profile,
    resolve_hermes_home,
    resolve_plugin_install_dir,
    resolve_plugin_skills_src,
    resolve_policy_profile,
    sync_project_env,
    normalize_optional_branch,
    overlay_path,
    read_overlay_config,
    resolve_branch_settings,
    resolve_coding_agent,
    resolve_coding_agent_model,
)
from .coding_agent import interactive_pick_model
from .hermes_model_config import (
    copy_active_model_to_profile,
    profile_has_model_config,
    read_active_model_config,
    read_model_config_from_config_show,
)
from .profile_bootstrap import (
    dispatch_profile_names,
    ensure_dispatch_profiles,
    reconcile_dispatch_profiles,
)

logger = logging.getLogger(__name__)

# Resolve paths relative to this plugin's repo root
PLUGIN_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")


def setup_argparse(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes kanban-advanced`` argparse tree.

    Called by Hermes at plugin load time. The subparser is already created —
    we add subcommands to it.
    """
    subs = subparser.add_subparsers(dest="subcommand")

    # ── decompose ──
    dec = subs.add_parser("decompose", help="Governed card creation from a plan")
    dec.add_argument("--plan", required=True, help="Path to plan markdown file")
    dec.add_argument("--board", default="default", help="Board slug")
    dec.add_argument("--dry-run", action="store_true", help="Validate without creating cards")

    # ── list ──
    lst = subs.add_parser("list", help="Board status")
    lst.add_argument("--status", help="Filter by status")
    lst.add_argument("--assignee", help="Filter by assignee")
    lst.add_argument("--json", action="store_true", default=True, help="JSON output")

    # ── show ──
    sh = subs.add_parser("show", help="Card details")
    sh.add_argument("task_id", help="Card ID")
    sh.add_argument("--json", action="store_true", default=True, help="JSON output")

    # ── validate ──
    val = subs.add_parser("validate", help="Pre-dispatch board validation")
    val.add_argument("--board", default="default", help="Board slug")

    # ── verify-optimization ──
    vo = subs.add_parser("verify-optimization", help="Plan optimization gate check")
    vo.add_argument("--plan", required=True, help="Path to plan markdown file")

    # ── preflight ──
    pf = subs.add_parser("preflight", help="Pre-decomposition environment gate")
    pf.add_argument("plan_id", help="Plan identifier")

    # ── init ──
    init = subs.add_parser("init", help="Post-install bootstrap for a project")
    init.add_argument("--project-root", default=".", help="Project root directory")
    init.add_argument("--working-branch", default=None, help="Integration branch (default: keep existing config, else git HEAD, else main)")
    init.add_argument("--trigger-branch", default=None, help="Optional protected branch agents must not push to (default: keep existing, else unset)")
    init.add_argument(
        "--policy-profile",
        default=None,
        choices=["advisory", "balanced", "strict"],
        help="Governance enforcement: advisory (warn), balanced (default), strict (block+notify)",
    )
    init.add_argument("--force", action="store_true", help="Skip confirmation prompts")

    subparser.set_defaults(func=handle_kanban)


def handle_kanban(args: argparse.Namespace) -> int:
    """Route to the correct subcommand handler. Returns exit code."""
    handlers = {
        "decompose": _handle_decompose,
        "list": _handle_list,
        "show": _handle_show,
        "validate": _handle_validate,
        "verify-optimization": _handle_verify_optimization,
        "preflight": _handle_preflight,
        "init": _handle_init,
    }

    handler = handlers.get(args.subcommand)
    if handler is None:
        print(f"Unknown subcommand: {args.subcommand}", file=sys.stderr)
        return 1

    try:
        return handler(args)
    except Exception as exc:
        logger.error("Subcommand %s failed: %s", args.subcommand, exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


# ── Subcommand handlers ──────────────────────────────────────────────


def _handle_decompose(args) -> int:
    """Run governed decomposition from a plan file."""
    script = SCRIPTS_DIR / "kanban_decompose.py"
    if not script.exists():
        print(f"Error: decomposition script not found at {script}", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(script), "--plan", args.plan]
    if args.dry_run:
        cmd.append("--dry-run")

    return subprocess.call(cmd)


def _handle_list(args) -> int:
    """Delegate to built-in hermes kanban list."""
    cmd = [HERMES_BIN, "kanban", "list"]
    if args.status:
        cmd.extend(["--status", args.status])
    if args.assignee:
        cmd.extend(["--assignee", args.assignee])
    if args.json:
        cmd.append("--json")
    return subprocess.call(cmd)


def _handle_show(args) -> int:
    """Delegate to built-in hermes kanban show."""
    cmd = [HERMES_BIN, "kanban", "show", args.task_id]
    if args.json:
        cmd.append("--json")
    return subprocess.call(cmd)


def _handle_validate(args) -> int:
    """Run pre-dispatch board validation."""
    script = SCRIPTS_DIR / "validate_board.sh"
    if not script.exists():
        print(f"Error: validation script not found at {script}", file=sys.stderr)
        return 1

    return subprocess.call(["bash", str(script)])


def _handle_verify_optimization(args) -> int:
    """Run plan optimization gate check."""
    script = SCRIPTS_DIR / "verify_optimization.sh"
    if not script.exists():
        print(f"Error: verify-optimization script not found at {script}", file=sys.stderr)
        return 1

    return subprocess.call(["bash", str(script), args.plan])


def _handle_preflight(args) -> int:
    """Run pre-decomposition environment gate."""
    script = SCRIPTS_DIR / "pre_dispatch_gate.sh"
    if not script.exists():
        print(f"Error: preflight script not found at {script}", file=sys.stderr)
        return 1

    return subprocess.call(["bash", str(script), args.plan_id])

def _handle_init(args) -> int:
    """Post-install bootstrap for a project — interactive, step-by-step.

    Each step must complete before moving to the next. Walks through
    profile creation, model configuration, max_turns tuning, config
    overlay, cron scripts, skill bundle, env setup, and gateway check.
    Cron jobs are handled by the agent during preflight/cleanup.
    Does not report "ready" until every step passes.
    """
    project_root = Path(args.project_root).resolve()
    hermes_home = resolve_hermes_home(project_root)
    plugin_root = resolve_plugin_install_dir()
    force = args.force
    config_file = overlay_path(project_root)
    existing_config = read_overlay_config(config_file)

    working_branch, trigger_branch, kept_existing = resolve_branch_settings(
        project_root,
        working_branch=args.working_branch,
        trigger_branch=args.trigger_branch,
        working_branch_specified=args.working_branch is not None,
        trigger_branch_specified=args.trigger_branch is not None,
    )

    if args.trigger_branch is None and not existing_config.get("trigger_branch") and not force:
        try:
            raw = input("   Protected branch (optional — agents must NOT push here): ").strip()
            if raw:
                trigger_branch = normalize_optional_branch(raw)
        except (EOFError, KeyboardInterrupt):
            pass

    print(f"kanban-advanced init -- bootstrapping {project_root}")
    print(f"   HERMES_HOME: {hermes_home}")
    print(f"  HERMES_HOME: {hermes_home}")
    print(f"  Working branch: {working_branch}")
    print(f"  Trigger branch: {trigger_branch or '(none — optional protected branch not set)'}")
    if kept_existing and config_file.is_file():
        print("  (preserved from existing kanban-config.yaml — pass --working-branch / --trigger-branch to override)")
    print()

    def _yn(prompt: str) -> bool:
        if force:
            return True
        try:
            return input(prompt + " [y/N] ").strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    def _run(cmd: list[str], timeout: int = 15, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, env=env,
        )

    # ── 1. Profiles ──────────────────────────────────────────────────
    print("1. Checking profiles...")
    worker_profile, orchestrator_profile = dispatch_profile_names(existing_config)
    dispatch_profiles = [worker_profile, orchestrator_profile]
    if not ensure_dispatch_profiles(
        _run,
        HERMES_BIN,
        hermes_home=hermes_home,
        force=force,
        prompt_yes_no=_yn,
        log=print,
    ):
        return 1

    # ── 1a. Model config ─────────────────────────────────────────────
    print()
    print("1a. Checking profile model config...")
    active_model = read_active_model_config(_run, HERMES_BIN)
    default_model = active_model.get("default", "")
    default_provider = active_model.get("provider", "")
    suggestion = (
        f"{default_provider}/{default_model}"
        if default_provider and default_model
        else (default_model or "none found")
    )

    for profile in dispatch_profiles:
        try:
            r = _run([HERMES_BIN, "-p", profile, "config", "show"])
            has_model = profile_has_model_config(
                read_model_config_from_config_show(r.stdout)
            )
        except Exception:
            has_model = False
        if has_model:
            print(f"   OK {profile}: model configured")
        else:
            print(f"   !  {profile}: no model configured")
            print(f"      Current profile uses: {suggestion}")
            if profile_has_model_config(active_model) and _yn(
                f"   Copy current model config to {profile}?"
            ):
                copy_active_model_to_profile(_run, HERMES_BIN, profile)
                print(f"   OK {profile} configured (copied from current profile)")
            elif _yn(f"   Launch interactive model picker for {profile}?"):
                print(f"   Run this in another terminal, then press Enter here to continue:")
                print(f"     hermes -p {profile} model")
                try:
                    input("   Press Enter when done...")
                except (EOFError, KeyboardInterrupt):
                    pass
                print(f"   OK continuing")
            else:
                print(f"   !  Skipped. Configure later: hermes -p {profile} model")

    # ── 1b. Max turns ────────────────────────────────────────────────
    print()
    print(f"1b. Checking {orchestrator_profile} max_turns...")
    try:
        r = _run([HERMES_BIN, "-p", orchestrator_profile, "config", "show"])
        # Hermes reads max_turns from agent.max_turns, not model.max_turns
        mt = re.search(r"Max turns:\s*(\d+)", r.stdout)
        max_turns = int(mt.group(1)) if mt else 90
    except Exception:
        max_turns = 90
    if max_turns >= 180:
        print(f"   OK {orchestrator_profile}: max_turns = {max_turns}")
    else:
        print(
            f"   !  {orchestrator_profile}: max_turns = {max_turns} "
            "-- recommend 180 for complex plan decomposition"
        )
        if _yn(f"   Set max_turns to 180?"):
            _run([HERMES_BIN, "-p", orchestrator_profile, "config", "set", "agent.max_turns", "180"])
            print(f"   OK max_turns set to 180")
        else:
            print(
                f"   !  Skipped. Fix later: hermes -p {orchestrator_profile} "
                "config set agent.max_turns 180"
            )

    # ── 1c. Coding agent binary ──────────────────────────────────────
    print()
    print("1c. Configuring coding agent binary...")
    print("    Supported headless CLI coding agents:")
    print()
    print("    | # | Binary   | Source                   |")
    print("    |---|----------|--------------------------|")
    print("    | 1 | agent    | Cursor CLI               |")
    print("    | 2 | claude   | Claude Code              |")
    print("    | 3 | codex    | OpenAI Codex             |")
    print("    | 4 | grok     | superagent-ai/grok-cli   |")
    print("    | 5 | aider    | Aider-AI/aider           |")
    print("    | 6 | gemini   | google-gemini/gemini-cli |")
    print()

    coding_binary = resolve_coding_agent(project_root)
    choice = ""
    try:
        if force:
            choice = "1"
        else:
            choice = input("    Which coding agent is on PATH? [1-6, or type binary name, default=1/agent] ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    agent_map = {"1": "agent", "2": "claude", "3": "codex", "4": "grok", "5": "aider", "6": "gemini"}
    if choice in agent_map:
        coding_binary = agent_map[choice]
    elif choice:
        coding_binary = choice  # custom binary name

    # Verify it's actually on PATH
    found = False
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if (Path(path_dir) / coding_binary).exists():
            found = True
            break
    if found:
        print(f"   OK '{coding_binary}' found on PATH")
    else:
        print(f"   !  '{coding_binary}' not found on PATH — install it before dispatching workers")
    print(f"   coding_agent_binary: {coding_binary}")
    print("    Workers will use this binary when executing agent-prompt blocks.")

    coding_model = resolve_coding_agent_model(project_root)
    if existing_config.get("coding_agent_model") and not force:
        print(f"   coding_agent_model: {coding_model} (preserved from config)")
    else:
        coding_model = interactive_pick_model(
            coding_binary,
            _run,
            default=coding_model,
            force=force,
        )

    # ── 1d. Governance policy profile ───────────────────────────────
    print()
    print("1d. Governance enforcement level...")
    print("    | # | Profile  | Behavior                          |")
    print("    |---|----------|-----------------------------------|")
    print("    | 1 | balanced | Block violations (default)        |")
    print("    | 2 | advisory | Warn only — human-supervised      |")
    print("    | 3 | strict   | Block + notify — walk-away runs   |")
    print()

    if args.policy_profile:
        policy_profile = normalize_policy_profile(args.policy_profile)
    elif existing_config.get("policy_profile") and not force:
        policy_profile = normalize_policy_profile(existing_config["policy_profile"])
    elif not force and not existing_config.get("policy_profile"):
        policy_profile = resolve_policy_profile(project_root)
        try:
            pchoice = input(
                "    Governance profile [1=balanced, 2=advisory, 3=strict, default=1]: "
            ).strip()
            policy_map = {"1": "balanced", "2": "advisory", "3": "strict", "": "balanced"}
            policy_profile = normalize_policy_profile(
                policy_map.get(pchoice, pchoice or "balanced")
            )
        except (EOFError, KeyboardInterrupt):
            policy_profile = resolve_policy_profile(project_root)
    else:
        policy_profile = resolve_policy_profile(project_root)
    print(f"   policy_profile: {policy_profile}")

    # ── 2. Config overlay ────────────────────────────────────────────
    print()
    print("2. Creating config overlay...")
    overlay_dir = config_file.parent
    overlay_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        build_overlay_yaml(
            working_branch=working_branch,
            trigger_branch=trigger_branch,
            coding_agent=coding_binary,
            coding_agent_model=coding_model,
            policy_profile=policy_profile,
            bundle_path=plugin_root,
            hermes_home=hermes_home,
            existing=existing_config,
        ),
        encoding="utf-8",
    )
    print(f"   OK {config_file}")

    # ── 2a. Materialize skills so skill_view() can resolve them ────────
    print("2a. Materializing skills...")
    skills_src = resolve_plugin_skills_src()
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
        print(f"   OK {count} skills -> {skills_dst}")
    else:
        print(f"   X Skills not found at {skills_src}")
        return 1

    # ── 2b. Reconcile profiles: rename → seed role skills → verify+fix ─
    # Dispatch profiles are created with `--no-skills` (no Hermes bundled skills).
    # reconcile_dispatch_profiles installs plugin SOUL.md prompts, seeds role-only
    # skills, writes `.no-bundled-skills`, then VERIFIES and reseeds once if needed.
    worker_profile, orchestrator_profile = dispatch_profile_names(
        read_overlay_config(config_file)
    )
    print("2b. Reconciling profiles (name prefix + role-only skills + verify)...")
    if not reconcile_dispatch_profiles(
        _run,
        HERMES_BIN,
        hermes_home,
        skills_src,
        worker_profile,
        orchestrator_profile,
        force=True,
        log=print,
    ):
        print("   X Profile reconciliation failed — see issues above.")
        return 1

    # ── 3. Cron scripts + token tracker ───────────────────────────────
    print("3. Provisioning cron scripts + token tracker...")
    cron_dir = hermes_home / "scripts"
    cron_dir.mkdir(parents=True, exist_ok=True)
    for script_name in ["auto_unblock.sh", "board_keeper.sh", "token_tracker.py"]:
        src = SCRIPTS_DIR / script_name
        dst = cron_dir / script_name
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            dst.chmod(0o755)
            print(f"   OK {script_name} -> {dst}")
        else:
            print(f"   X {script_name} not found at {src}")
            return 1

    # ── 4. Env ───────────────────────────────────────────────────────
    print("4. Setting project .env (plugins, coding agent, governance profile)...")
    sync_project_env(
        project_root,
        {
            "HERMES_ENABLE_PROJECT_PLUGINS": "true",
            "KANBAN_CODING_AGENT": coding_binary,
            "KANBAN_CODING_AGENT_MODEL": coding_model,
            "KANBAN_POLICY_PROFILE": policy_profile,
        },
    )
    print("   OK")

    # ── 5. Dispatcher config ─────────────────────────────────────────
    # Disable the built-in auto-decomposer so triage cards are not rewritten
    # by Hermes' LLM before the orchestrator reviews them, and so a dispatched
    # orchestrator-handoff card runs the governed decomposition SOP instead of
    # being LLM-decomposed into stub children.
    print("5. Configuring dispatcher (kanban.auto_decompose=false)...")
    r_ad = _run([HERMES_BIN, "config", "set", "kanban.auto_decompose", "false"])
    if r_ad.returncode == 0:
        print("   OK kanban.auto_decompose = false")
    else:
        print("   !  Could not set kanban.auto_decompose — set manually: hermes config set kanban.auto_decompose false")

    # ── 6. Gateway ───────────────────────────────────────────────────
    print("6. Checking gateway...")
    gateway_ok = False
    try:
        r = _run([HERMES_BIN, "gateway", "status"])
        if r.returncode == 0:
            stdout = r.stdout
            if "outdated" in stdout.lower():
                print("   !  Gateway running but service definition is outdated")
                if _yn("   Restart gateway now to update?"):
                    _run([HERMES_BIN, "gateway", "restart"], timeout=30)
                    print("   OK Gateway restarted")
                else:
                    print("   !  Skipped. Run: hermes gateway restart")
            else:
                print("   OK Gateway running")
            gateway_ok = True
        else:
            print("   !  Gateway not running")
            if _yn("   Start gateway now?"):
                print("   Starting gateway (this may take a moment)...")
                r2 = subprocess.run(
                    [HERMES_BIN, "gateway", "run"],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=5
                )
                if r2.returncode == 0:
                    print("   OK Gateway started")
                    gateway_ok = True
                else:
                    print(f"   X Could not start gateway. Start manually: hermes gateway run")
            else:
                print("   !  Start manually: hermes gateway run")
    except Exception as exc:
        print(f"   X Could not check gateway: {exc}")

    # ── Readiness ────────────────────────────────────────────────────
    print()
    print("=" * 50)
    print("OK kanban-advanced is ready!")
    print(f"  Config: {config_file}")
    print(f"  Cron scripts: {cron_dir}")
    print(f"  Profiles: {DEFAULT_WORKER_PROFILE}, {DEFAULT_ORCHESTRATOR_PROFILE}")
    print(f"  Coding agent: {coding_binary}")
    print(f"  Governance profile: {policy_profile}")
    if not gateway_ok:
        print()
        print("  Before your first plan:")
        print(f"    hermes gateway run")
    return 0
