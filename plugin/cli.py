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
import subprocess
import sys
import os
from pathlib import Path

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
    init.add_argument("--working-branch", default="main", help="Integration branch for worktrees (e.g. main, master)")
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
    """Post-install bootstrap for a project.

    Provisions:
    1. Verifies profiles (worker, orchestrator)
    2. Creates config overlay
    3. Provisions cron scripts to $HERMES_HOME/scripts/
    4. Registers skill bundle for non-plugin Hermes sessions
    5. Sets HERMES_ENABLE_PROJECT_PLUGINS=true
    6. Verifies gateway
    7. Outputs readiness report
    """
    project_root = Path(args.project_root).resolve()
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

    print(f"kanban-advanced init -- bootstrapping {project_root}")
    print(f"  HERMES_HOME: {hermes_home}")
    print(f"  Working branch: {args.working_branch}")
    print()

    errors = []

    # 1. Verify profiles exist
    print("1. Checking profiles...")
    try:
        result = subprocess.run(
            [HERMES_BIN, "profile", "list"],
            capture_output=True, text=True, timeout=10
        )
        profiles_output = result.stdout
    except Exception:
        profiles_output = ""

    for profile in ["worker", "orchestrator"]:
        if profile not in profiles_output:
            msg = f"   Profile '{profile}' not found. Create it with: hermes profile create {profile}"
            print(f"   X {msg}")
            errors.append(msg)
        else:
            print(f"   OK {profile}")

    # 1a. Check profile model config
    print()
    print("1a. Checking profile model config...")
    for profile in ["worker", "orchestrator"]:
        try:
            result = subprocess.run(
                [HERMES_BIN, "-p", profile, "config", "get", "model.default"],
                capture_output=True, text=True, timeout=10
            )
            model = result.stdout.strip()
            if model and model != "None":
                print(f"   OK {profile}: model.default = {model}")
            else:
                print(f"   !  {profile}: no model configured")
                print(f"      Fix: hermes -p {profile} config set model.default <model-name>")
                print(f"           hermes -p {profile} config set model.provider <provider-name>")
                if profile == "orchestrator":
                    print(f"           hermes -p {profile} config set model.base_url <url>  # if needed")
        except Exception:
            pass

    # 1b. Check orchestrator max_turns
    print()
    print("1b. Checking orchestrator max_turns...")
    try:
        result = subprocess.run(
            [HERMES_BIN, "-p", "orchestrator", "config", "get", "model.max_turns"],
            capture_output=True, text=True, timeout=10
        )
        max_turns = result.stdout.strip()
        if max_turns and max_turns.isdigit() and int(max_turns) >= 180:
            print(f"   OK orchestrator: max_turns = {max_turns}")
        else:
            current = max_turns if max_turns else "default (90)"
            print(f"   !  orchestrator: max_turns = {current} -- recommend 180 for complex plans")
            print(f"      Fix: hermes -p orchestrator config set model.max_turns 180")
    except Exception:
        pass

    # 2. Create config overlay
    print("2. Creating config overlay...")
    overlay_dir = project_root / ".hermes" / "kanban-overrides"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    config_file = overlay_dir / "kanban-config.yaml"
    config_file.write_text(f"""# kanban-advanced config overlay -- generated by kanban-advanced init
working_branch: {args.working_branch}
bundle_path: {PLUGIN_ROOT}
skills_output_path: {hermes_home / 'skills' / 'devops'}
profiles:
  orchestrator: orchestrator
  worker: worker
""")
    print(f"   OK {config_file}")

    # 3. Provision cron scripts
    print("3. Provisioning cron scripts...")
    cron_dir = hermes_home / "scripts"
    cron_dir.mkdir(parents=True, exist_ok=True)

    for script_name in ["auto_unblock.sh", "board_keeper.sh"]:
        src = SCRIPTS_DIR / script_name
        dst = cron_dir / script_name
        if src.exists():
            dst.write_text(src.read_text())
            dst.chmod(0o755)
            print(f"   OK {script_name} -> {dst}")
        else:
            msg = f"   X {script_name} not found at {src}"
            print(msg)
            errors.append(msg)

    # 4. Register skill bundle (for non-plugin Hermes sessions)
    print("4. Registering skill bundle...")
    bundle_src = PLUGIN_ROOT / "bundles" / "kanban-advanced.yaml"
    bundle_dir = hermes_home / "skill-bundles"
    bundle_dst = bundle_dir / "kanban-advanced.yaml"

    if bundle_src.exists():
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_dst.write_text(bundle_src.read_text())
        print(f"   OK kanban-advanced.yaml -> {bundle_dst}")

        # Reload bundles if hermes is available
        try:
            subprocess.run(
                [HERMES_BIN, "bundles", "reload"],
                capture_output=True, text=True, timeout=10
            )
            print("   OK bundles reloaded")
        except Exception:
            print("   X Could not reload bundles (hermes may not be running)")
    else:
        msg = f"   X Bundle not found at {bundle_src}"
        print(msg)
        errors.append(msg)

    # 5. Set HERMES_ENABLE_PROJECT_PLUGINS
    print("5. Setting HERMES_ENABLE_PROJECT_PLUGINS=true...")
    env_file = project_root / ".env"
    env_line = "HERMES_ENABLE_PROJECT_PLUGINS=true\n"

    if env_file.exists():
        content = env_file.read_text()
        if "HERMES_ENABLE_PROJECT_PLUGINS" not in content:
            env_file.write_text(content + env_line)
            print("   OK Added to .env")
        else:
            print("   OK Already set in .env")
    else:
        env_file.write_text(env_line + "\n")
        print("   OK Created .env with setting")

    # 6. Verify gateway
    print("6. Checking gateway...")
    try:
        result = subprocess.run(
            [HERMES_BIN, "gateway", "status"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"   OK Gateway: {result.stdout.strip()}")
        else:
            msg = "Gateway not running -- start with 'hermes gateway start'"
            print(f"   X {msg}")
            errors.append(msg)
    except Exception as exc:
        msg = f"Could not check gateway: {exc}"
        print(f"   X {msg}")
        errors.append(msg)

    # 7. Readiness report
    print()
    print("=" * 50)
    if errors:
        print("WARNING Bootstrap complete with warnings:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("OK kanban-advanced is ready!")
        print(f"  Config: {config_file}")
        print(f"  Cron scripts: {cron_dir}")
        print(f"  Skill bundle: {bundle_dst}")
        print(f"  Profiles: worker, orchestrator")
        print()
        print("  Next steps:")
        print(f"    1. Configure profile models if not set (see check 1a above)")
        print(f"    2. Set up cron jobs for autonomous operation:")
        print(f"       hermes cronjob create --schedule \"every 1m\" --script \"auto_unblock.sh\" --no-agent --name kanban-auto-unblock")
        print(f"       hermes cronjob create --schedule \"every 3m\" --script \"board_keeper.sh\" --no-agent --name kanban-board-keeper")
        print(f"    3. Start gateway: hermes gateway start")
        print(f"    4. Decompose a plan: hermes kanban-advanced decompose --plan <file>")
        return 0
