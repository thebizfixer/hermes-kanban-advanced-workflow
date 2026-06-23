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

from .hermes_kanban_bootstrap import apply_hermes_kanban_bootstrap_config
from .config_overlay import (
    DEFAULT_ORCHESTRATOR_PROFILE,
    DEFAULT_WORKER_PROFILE,
    build_overlay_yaml,
    normalize_policy_profile,
    resolve_hermes_home,
    resolve_plugin_install_dir,
    resolve_plugin_skills_src,
    resolve_policy_profile,
    sync_dispatch_runtime_env,
    sync_project_env,
    normalize_optional_branch,
    overlay_path,
    read_overlay_config,
    resolve_branch_settings,
    resolve_coding_agent,
    resolve_coding_agent_model,
)
from .coding_agent import (
    CONFLICT_HINT,
    CONFLICT_MESSAGE,
    INIT_PREAMBLE,
    binary_on_path,
    get_available_coding_binaries,
    interactive_pick_model,
    is_contested_binary_name,
)
from .hermes_model_config import (
    copy_active_model_to_profile,
    profile_has_model_config,
    read_active_model_config,
    read_model_config_from_config_show,
    read_reasoning_effort_from_config_show,
    seed_default_reasoning_effort_for_profile,
)
from .profile_bootstrap import (
    dispatch_profile_names,
    ensure_dispatch_profiles,
    materialize_skill_dir,
    reconcile_dispatch_profiles,
)
from .script_materialize import materialize_hermes_scripts, materialize_skills_with_preservation
from .worktree_provision import ensure_worktreeinclude

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

    print()
    print("1a-ii. Seeding default reasoning effort (when unset)...")
    for profile in dispatch_profiles:
        seeded = seed_default_reasoning_effort_for_profile(
            _run,
            HERMES_BIN,
            profile,
            orchestrator_profile=orchestrator_profile,
            worker_profile=worker_profile,
            log=print,
        )
        if seeded is None:
            try:
                r = _run([HERMES_BIN, "-p", profile, "config", "show"])
                info = read_reasoning_effort_from_config_show(r.stdout)
                if info.get("reasoning_effort_configured"):
                    print(
                        f"   OK {profile}: reasoning_effort = {info['reasoning_effort']}"
                    )
            except Exception:
                print(f"   !  {profile}: could not read reasoning_effort")

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
    avail = get_available_coding_binaries()
    print(f"    {INIT_PREAMBLE}")
    print()
    if avail:
        for i, item in enumerate(avail, 1):
            print(f"    | {i} | {item['command']:<14} | {item['label']} |")
    else:
        print("    (none detected — you can still type a custom command)")
    print("    | 0 | (custom)     | Other / type exact command name |")
    print()

    coding_binary = resolve_coding_agent(project_root)
    choice = ""
    try:
        if force:
            choice = "1" if avail else ""
        else:
            choice = input(
                "    Which (number), 0 for custom, or type exact command name? "
            ).strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    if choice.isdigit() and 1 <= int(choice) <= len(avail):
        coding_binary = str(avail[int(choice) - 1]["command"])
    elif choice and choice != "0":
        coding_binary = choice

    if binary_on_path(coding_binary):
        print(f"   OK '{coding_binary}' found on PATH")
    else:
        print(
            f"   !  '{coding_binary}' not found on PATH — "
            "install it before dispatching workers"
        )
    if is_contested_binary_name(coding_binary):
        print(f"   !  {CONFLICT_MESSAGE}")
        print(f"   !  {CONFLICT_HINT}")
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
            project_root=project_root,
        ),
        encoding="utf-8",
    )
    print(f"   OK {config_file}")

    # ── 2a. Materialize skills so skill_view() can resolve them ────────
    print("2a. Materializing skills...")
    skills_src = resolve_plugin_skills_src()
    skills_dst = hermes_home / "skills" / "kanban-advanced"
    data_refs = PLUGIN_ROOT / "plugin" / "data" / "references"
    count, skill_warnings = materialize_skills_with_preservation(
        skills_src,
        skills_dst,
        materialize_skill_dir=materialize_skill_dir,
        bundle_data_references=data_refs,
        log=print,
    )
    if count:
        print(f"   OK {count} skills -> {skills_dst}")
    for line in skill_warnings:
        print(line)
    if not count:
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

    # ── 3. Cron scripts + token tracker + coding-agent invoke helpers ─
    print("3. Provisioning cron scripts + token tracker...")
    cron_dir = hermes_home / "scripts"
    script_lines = materialize_hermes_scripts(SCRIPTS_DIR, cron_dir)
    if not script_lines:
        print(f"   X No scripts materialized from {SCRIPTS_DIR}")
        return 1
    for line in script_lines:
        print(line)

    print("3b. Ensuring .worktreeinclude for card worktrees...")
    for line in ensure_worktreeinclude(project_root, hermes_home):
        print(line)

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
    home_updates = sync_dispatch_runtime_env(project_root)
    if home_updates.get("HOME"):
        print(f"   OK HOME={home_updates['HOME']} (coding-agent credential paths)")
    else:
        print("   !  Could not resolve HOME — set HOME= in .env before gateway dispatch")
    print("   OK")

    # ── 5. Dispatcher config ─────────────────────────────────────────
    # Disable the built-in auto-decomposer; enable stale dispatch reclaim.
    # See plugin/data/references/dispatch-stale-timeout.md.
    print("5. Configuring Hermes kanban dispatcher...")
    apply_hermes_kanban_bootstrap_config(_run, HERMES_BIN, log=print)

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

    # ── 7. Dashboard server ───────────────────────────────────────────
    print("7. Dashboard server + keepalive cron...")
    server_script = cron_dir / "dashboard_server.py"
    keepalive_script = cron_dir / "dashboard_server_keepalive.sh"
    
    # Register keepalive cron for crash recovery (idempotent)
    if keepalive_script.exists():
        try:
            existing = subprocess.run(
                [HERMES_BIN, "cron", "list"],
                capture_output=True, text=True,
                env={**os.environ, "HERMES_HOME": str(hermes_home)},
                timeout=15,
            )
            if "kanban-dashboard-keepalive" not in (existing.stdout or ""):
                subprocess.run([
                    HERMES_BIN, "cron", "create", "60s",
                    "--name", "kanban-dashboard-keepalive",
                    "--no-agent",
                    "--script", str(keepalive_script),
                    "--deliver", "local",
                    "--repeat", "999",
                ], env={**os.environ, "HERMES_HOME": str(hermes_home)}, timeout=15)
                print(f"   OK Keepalive cron registered (crash recovery every 60s)")
            else:
                print(f"   OK Keepalive cron already registered")
        except Exception as exc:
            print(f"   !  Could not register keepalive cron: {exc}")
    
    # Start the server now (don't wait for cron)
    if server_script.exists():
        try:
            subprocess.Popen(
                ["python3", str(server_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"   OK Dashboard server started (port 18900)")
        except Exception as exc:
            print(f"   !  Could not start dashboard server: {exc}")
            print(f"   Start manually: python3 {server_script}")
    else:
        print(f"   !  Server script not found at {server_script}")

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
