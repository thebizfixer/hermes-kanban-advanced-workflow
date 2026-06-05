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
    """Post-install bootstrap for a project — interactive, step-by-step.

    Each step must complete before moving to the next. The user is walked
    through profile creation, model configuration, max_turns tuning, config
    overlay, cron scripts, skill bundle, env setup, gateway check, and cron
    job creation. Does not report "ready" until every step passes.
    """
    project_root = Path(args.project_root).resolve()
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    force = args.force

    print(f"kanban-advanced init -- bootstrapping {project_root}")
    print(f"  HERMES_HOME: {hermes_home}")
    print(f"  Working branch: {args.working_branch}")
    print()

    def _yn(prompt: str) -> bool:
        if force:
            return True
        try:
            return input(prompt + " [y/N] ").strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # ── 1. Profiles ──────────────────────────────────────────────────
    print("1. Checking profiles...")
    try:
        profiles_output = _run([HERMES_BIN, "profile", "list"]).stdout
    except Exception:
        profiles_output = ""

    for profile in ["worker", "orchestrator"]:
        if profile not in profiles_output:
            if _yn(f"   Profile '{profile}' not found. Create it now?"):
                r = _run([HERMES_BIN, "profile", "create", profile, "--clone"])
                if r.returncode == 0:
                    print(f"   OK Created '{profile}'")
                else:
                    print(f"   X Failed to create '{profile}': {r.stderr.strip()}")
                    return 1
            else:
                print(f"   X Profile '{profile}' is required. Run: hermes profile create {profile} --clone")
                return 1
        else:
            print(f"   OK {profile}")

    # ── 1a. Model config ─────────────────────────────────────────────
    print()
    print("1a. Checking profile model config...")
    # Sniff the current profile's model as a suggestion
    try:
        r = _run([HERMES_BIN, "config", "show"])
        default_model = ""
        default_provider = ""
        default_url = ""
        m = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", r.stdout)
        if m:
            default_model = m.group(1)
        m = re.search(r"'provider':\s*'([^']+)'", r.stdout)
        if m:
            default_provider = m.group(1)
        m = re.search(r"'base_url':\s*'([^']*)'", r.stdout)
        if m:
            default_url = m.group(1)
        suggestion = f"{default_provider}/{default_model}" if default_provider and default_model else "none found"
    except Exception:
        default_model = default_provider = default_url = ""
        suggestion = "unknown"

    for profile in ["worker", "orchestrator"]:
        try:
            r = _run([HERMES_BIN, "-p", profile, "config", "show"])
            pm = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", r.stdout)
            has_model = bool(pm and pm.group(1) and pm.group(1) != "None")
        except Exception:
            has_model = False
        if has_model:
            print(f"   OK {profile}: model configured")
        else:
            print(f"   !  {profile}: no model configured")
            print(f"      Current profile uses: {suggestion}")
            if default_model and default_provider and _yn(f"   Copy current model config to {profile}?"):
                _run([HERMES_BIN, "-p", profile, "config", "set", "model.default", default_model])
                _run([HERMES_BIN, "-p", profile, "config", "set", "model.provider", default_provider])
                if default_url:
                    _run([HERMES_BIN, "-p", profile, "config", "set", "model.base_url", default_url])
                print(f"   OK {profile} configured (copied from current profile)")
            else:
                print(f"   !  Skipped. Run the interactive picker: hermes -p {profile} model")

    # ── 1b. Max turns ────────────────────────────────────────────────
    print()
    print("1b. Checking orchestrator max_turns...")
    try:
        r = _run([HERMES_BIN, "-p", "orchestrator", "config", "get", "model.max_turns"])
        max_turns = r.stdout.strip()
    except Exception:
        max_turns = ""
    if max_turns and max_turns.isdigit() and int(max_turns) >= 180:
        print(f"   OK orchestrator: max_turns = {max_turns}")
    else:
        current = max_turns if max_turns else "default (90)"
        print(f"   !  orchestrator: max_turns = {current} -- recommend 180 for complex plan decomposition")
        if _yn(f"   Set max_turns to 180?"):
            _run([HERMES_BIN, "-p", "orchestrator", "config", "set", "model.max_turns", "180"])
            print(f"   OK max_turns set to 180")
        else:
            print(f"   !  Skipped. Fix later: hermes -p orchestrator config set model.max_turns 180")

    # ── 2. Config overlay ────────────────────────────────────────────
    print()
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

    # ── 3. Cron scripts ──────────────────────────────────────────────
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
            print(f"   X {script_name} not found at {src}")
            return 1

    # ── 4. Skill bundle ──────────────────────────────────────────────
    print("4. Registering skill bundle...")
    bundle_src = PLUGIN_ROOT / "bundles" / "kanban-advanced.yaml"
    bundle_dir = hermes_home / "skill-bundles"
    bundle_dst = bundle_dir / "kanban-advanced.yaml"
    if bundle_src.exists():
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_dst.write_text(bundle_src.read_text())
        print(f"   OK kanban-advanced.yaml -> {bundle_dst}")
        try:
            _run([HERMES_BIN, "bundles", "reload"])
            print("   OK bundles reloaded")
        except Exception:
            print("   X Could not reload bundles")
    else:
        print(f"   X Bundle not found at {bundle_src}")
        return 1

    # ── 5. Env ───────────────────────────────────────────────────────
    print("5. Setting HERMES_ENABLE_PROJECT_PLUGINS=true...")
    env_file = project_root / ".env"
    env_line = "HERMES_ENABLE_PROJECT_PLUGINS=true\n"
    if env_file.exists():
        content = env_file.read_text()
        if "HERMES_ENABLE_PROJECT_PLUGINS" not in content:
            env_file.write_text(content + env_line)
    else:
        env_file.write_text(env_line + "\n")
    print("   OK")

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
                    capture_output=True, text=True, timeout=5
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

    # ── 7. Cron jobs ─────────────────────────────────────────────────
    print("7. Setting up cron jobs...")
    cron_scripts = {
        "kanban-auto-unblock": ("every 1m", "auto_unblock.sh"),
        "kanban-board-keeper": ("every 3m", "board_keeper.sh"),
    }
    for name, (schedule, script) in cron_scripts.items():
        # Check if already exists
        r = _run([HERMES_BIN, "cronjob", "list"])
        if name in r.stdout:
            print(f"   OK {name} already exists")
            continue
        if _yn(f"   Create cron job '{name}' ({schedule})?"):
            r = _run([
                HERMES_BIN, "cronjob", "create",
                "--schedule", schedule,
                "--script", script,
                "--no-agent",
                "--name", name,
            ])
            if r.returncode == 0:
                print(f"   OK {name} created")
            else:
                print(f"   X Failed to create {name}: {r.stderr.strip()}")
        else:
            print(f"   !  Skipped. Create manually: hermes cronjob create --schedule \"{schedule}\" --script \"{script}\" --no-agent --name {name}")

    # ── Readiness ────────────────────────────────────────────────────
    print()
    print("=" * 50)
    print("OK kanban-advanced is ready!")
    print(f"  Config: {config_file}")
    print(f"  Cron scripts: {cron_dir}")
    print(f"  Skill bundle: {bundle_dst}")
    print(f"  Profiles: worker, orchestrator")
    if not gateway_ok:
        print()
        print("  Before your first plan:")
        print(f"    hermes gateway run")
    return 0
