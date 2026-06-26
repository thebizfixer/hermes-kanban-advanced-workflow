#!/usr/bin/env python3
"""
kanban_decompose.py — Governed card creation from a hardened, optimized plan.

Reads card definitions from a plan's "Kanban optimization" section and creates
them on the kanban board in governed order:

  1. Create gate card (ready), then block it immediately (beats the dispatcher)
  2. Create each implementation card (ready), block it immediately
  3. Link dependencies: gate → all impl cards; wave_parent → child; ordinal_parent → child
  4. Link all impl cards → audit card (blocked on create); create + complete root card
  5. Verify all parent links exist
  6. Print gate ID and orchestrator next-steps

Vanilla hermes creates cards in 'ready' status and the dispatcher claims ready
cards in under a second. Each card is therefore blocked immediately after
creation. Dependency gating is driven by auto_unblock.sh (cron, every 1m), which
unblocks a card only once all its parents are done. Since the gate is a parent of
every implementation card, completing the gate releases wave 1; later waves
release as their wave/ordinal parents complete.

The gate card is an orchestrator control card — NOT a human checkpoint.
The orchestrator runs validate_board.sh, then `hermes kanban complete <gate_id>`
to release wave 1. Workers never see or interact with the gate card.

Avoid --initial-status blocked (buggy: auto-promotes under race conditions) and
--triage for dependent cards (only the dispatcher can promote triage; they get
stuck when auto_decompose is off). Block-on-create is the supported path.

Usage:
    python3 kanban_decompose.py --plan <plan.md> [--dry-run] [--no-crons]
    python3 kanban_decompose.py --plan <plan.md> --json  (machine-readable output)

The plan must have a "## Kanban optimization" section with "#### Card N" subsections
containing YAML-frontmatter card bodies (plan_id, files, mode, tests, commit,
estimated_lines, assignee, wave, wave_parent, ordinal_parent).

Environment:
    HERMES_HOME — required; used to locate kanban.db and cron script paths
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.plan_parse import (  # noqa: E402
    _extract_markdown_field,
    _extract_markdown_files,
    _extract_optimization_section,
    _extract_plan_id_from_content,
    _split_card_blocks,
    parse_card_block,
    parse_plan,
)
from lib.decompose_stamp import stamp_all_impl_cards  # noqa: E402

# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Governed kanban card creation from plan")
    p.add_argument("--plan", help="Path to the optimized plan file (markdown)")
    p.add_argument("--cards-yaml", help="Path to structured cards YAML file (preferred)")
    p.add_argument("--dry-run", action="store_true", help="Parse and print cards, don't create")
    p.add_argument("--no-crons", action="store_true", help="Skip cron check (handoff path)")
    p.add_argument(
        "--provision-crons",
        action="store_true",
        help="Create wave crons (manual orchestrator decomposition without handoff) — DEPRECATED outside handoff.py",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument("--archive-prior", action="store_true",
                   help="Archive non-running plan cards before decompose (exit 7 if any running)")
    p.add_argument("--stagger-ms", type=int, default=1500,
                   help="Millis between card creates (default: 1500)")
    p.add_argument("--pause-every", type=int, default=5,
                   help="Pause after every N cards (default: 5)")
    p.add_argument("--pause-ms", type=int, default=3000,
                   help="Pause duration in millis (default: 3000)")
    p.add_argument("--from-handoff", action="store_true",
                   help="Internal: only set by kanban_handoff.py. Direct use is a governance violation.")
    p.add_argument("--gate-id", help="Reuse existing gate card (from handoff runbook Step 2)")

    args = p.parse_args()
    if not args.plan and not args.cards_yaml:
        p.error("Either --plan or --cards-yaml is required")

    # Hard governance guard: direct decompose is forbidden except in explicit recovery/debug.
    # Future users / agents must go through kanban_handoff.py which creates the single
    # Type: orchestrator-handoff card. This prevents duplicate roots, duplicate gates,
    # manual ROOT bypasses, and incorrect cron/notify handling.
    if not args.from_handoff and not args.dry_run:
        # Allow only if the caller is clearly the orchestrator in a controlled recovery
        # (we still warn loudly). In normal operation this should never be reached.
        print("ERROR: kanban_decompose.py was invoked directly (no --from-handoff).", file=sys.stderr)
        print("This is a governance violation.", file=sys.stderr)
        print("The only supported path is: python kanban_handoff.py --plan <plan.md>", file=sys.stderr)
        print("Direct decompose bypasses handoff card, idempotency, cron provisioning in the", file=sys.stderr)
        print("correct session, Type: orchestrator-handoff marker, and board-clean checks.", file=sys.stderr)
        print("It is the root cause of duplicate cards, duplicate roots/gates, and config drift.", file=sys.stderr)
        print("", file=sys.stderr)
        print("If you are debugging, re-run via handoff.py or use --dry-run.", file=sys.stderr)
        sys.exit(9)  # New exit code for "direct decompose bypass"

    return args

# ── Plan parser ────────────────────────────────────────────────────────────

def parse_yaml_cards(yaml_path: str) -> dict:
    """Parse card definitions from a structured YAML file (preferred format)."""
    import yaml
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "cards" not in data:
        sys.exit("ERROR: YAML file must have a 'cards' key")

    cards = []
    for raw in data["cards"]:
        card = {
            "key": raw.get("key", ""),
            "title": raw.get("title", ""),
            "type": raw.get("type", "code-gen"),
            "assignee": raw.get("assignee", "worker"),
            "plan_id": data.get("plan_id", raw.get("plan_id", "")),
            "files": raw.get("files", []),
            "mode": raw.get("mode", "modify-only"),
            "tests": raw.get("tests", ""),
            "commit": raw.get("commit", ""),
            "estimated_lines": raw.get("estimated_lines", 0),
            "wave": raw.get("wave", 1),
            "wave_parent": raw.get("wave_parent"),
            "ordinal_parent": raw.get("ordinal_parent"),
            "workspace": raw.get("workspace"),
            "branch": raw.get("branch"),
            "body": raw.get("body", ""),
            "agent_body": raw.get("body", ""),  # same as body for YAML format
        }
        cards.append(card)

    return {"cards": cards, "plan_id": data.get("plan_id", "")}


def _find_project_kanban_dir(start: Path) -> Path | None:
    for parent in [start.resolve(), *start.resolve().parents]:
        kanban = parent / ".hermes" / "kanban"
        if kanban.is_dir():
            return kanban
    return None


def update_plan_memory(
    plan_path: str,
    plan_id: str,
    impl_card_count: int,
    task_ids: dict[str, str] | None = None,
) -> None:
    """Refresh plan memory metadata after a successful parse/decompose."""
    import hashlib
    from datetime import datetime, timezone

    plan_file = Path(plan_path).resolve()
    content = plan_file.read_bytes()
    plan_sha = hashlib.sha256(content).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    mem_dir = _find_project_kanban_dir(plan_file.parent)
    if mem_dir is None:
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        mem_dir = hermes_home / "kanban" / "memory"
    else:
        mem_dir = mem_dir / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_path = mem_dir / f"{plan_id}.json"

    acceptance_matrix: dict = {}
    if plan_path and Path(plan_path).is_file():
        try:
            from lib.decompose_stamp import load_acceptance_matrix  # noqa: E402

            acceptance_matrix = load_acceptance_matrix(plan_path)
        except Exception:
            acceptance_matrix = {}

    data: dict = {}
    if mem_path.is_file():
        try:
            data = json.loads(mem_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}

    data.update(
        {
            "plan_id": plan_id,
            "plan_path": str(plan_file),
            "card_count": impl_card_count,
            "optimized_at": stamp,
            "plan_sha256": plan_sha,
        }
    )
    if task_ids:
        data["task_ids"] = list(task_ids.values())
        data["task_ids_by_key"] = task_ids
        data["card_task_ids"] = task_ids
        branches = {
            key: f"wt/{tid}" for key, tid in task_ids.items() if key not in ("gate", "root", "audit")
        }
        if branches:
            data["card_branches"] = branches
    if acceptance_matrix:
        data["acceptance_matrix"] = acceptance_matrix

    mem_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  Plan memory updated: {mem_path} ({impl_card_count} impl cards)")


# ── Kanban operations ──────────────────────────────────────────────────────

def hermes(*args, timeout: int = 30) -> tuple[str, str, int]:
    """Run a hermes CLI command."""
    cmd = ["hermes"] + list(args)
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def extract_id(output: str) -> str | None:
    """Extract task ID from hermes output (e.g., t_a1b2c3d4)."""
    m = re.search(r'(t_[a-zA-Z0-9]{8})', output)
    return m.group(1) if m else None


def parse_create_task_id(stdout: str) -> str | None:
    """Parse task id from hermes kanban create --json or text output."""
    stdout = stdout.strip()
    if stdout.startswith("{"):
        try:
            data = json.loads(stdout)
            tid = data.get("id")
            if tid:
                return str(tid)
        except json.JSONDecodeError:
            pass
    return extract_id(stdout)


def create_card_timeout_seconds(body: str) -> int:
    """Scale create timeout for large card bodies."""
    nbytes = len(body.encode("utf-8"))
    return 30 + max(0, (nbytes - 4096) // 4096) * 5


def estimate_turn_budget(card: dict) -> int:
    """Rough happy-path turn estimate (kanban-planning Optimize formula)."""
    body = card.get("body", "") or ""
    lines = int(card.get("estimated_lines", 0) or 0)
    fn_count = len(re.findall(r"\b(?:def |class |async def )", body))
    test_runs = min(body.lower().count("pytest") + body.lower().count("npm test"), 3)
    consumer_checks = body.lower().count("call-sites:")
    return (fn_count * 3) + (test_runs * 2) + (consumer_checks * 2) + (2 if lines > 80 else 0) + 2


def _is_dispatcher_absolute(path: str) -> bool:
    """Return True if path is absolute per Hermes dispatcher requirements.
    On Windows, paths must start with a drive letter. On Unix, os.path.isabs() suffices."""
    import sys, re
    if sys.platform == 'win32':
        return bool(re.match(r'^[A-Za-z]:[/\\\\]', path))
    return os.path.isabs(path)


def max_retries_for_card(card: dict) -> int:
    """Per-plan cap: always ≤2 retries for code-gen cards."""
    if card.get("type") != "code-gen":
        return 2
    return 2


def create_card(card: dict, dry_run: bool = False, block_after: bool = False, run_ts: str = "") -> str | None:
    """Create a single kanban card. Returns task ID or None.

    Vanilla hermes creates cards in 'ready' status and the dispatcher claims
    ready cards in under a second. When block_after is True, the card is blocked
    immediately after creation (before any stagger sleep) to close that race
    window. Dependency gating is then driven by auto_unblock.sh, which unblocks
    a card only once all its parents are done.
    """
    title = card["title"]
    assignee = card["assignee"]
    card_type = card["type"]
    body = card["body"]

    if card_type == "code-gen" and "Iteration-budget:" not in body:
        est = estimate_turn_budget(card)
        body = f"Iteration-budget: ~{est} turns (happy-path cap 35; max-retries: 2)\n\n{body}"
        card["body"] = body

    if dry_run:
        suffix = " then block" if block_after else ""
        print(f"  [DRY-RUN] Would create: {title} (assignee={assignee}, type={card_type}){suffix}")
        return f"dryrun_{card['key']}"

    # Write body to temp file to avoid shell escaping
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding="utf-8") as f:
        f.write(body)
        tmpfile = f.name

    try:
        cmd = ["hermes", "kanban", "create", title, "--assignee", assignee]

        # Code-gen cards must run in a worktree, not scratch.  Default to
        # worktree with an auto-generated branch when the plan omits them.
        if card_type == "code-gen":
            plan_id = card.get("plan_id", "plan")
            card_key = card.get("key", "card")
            workspace = card.get("workspace")
            if not workspace or workspace == "worktree":
                # Auto-generate worktree path when plan doesn't specify one.
                # "worktree" alone is rejected by the dispatcher — must have :<path>.
                # Use platform-appropriate temp dir (C:\Users\...\Temp on Windows, /tmp on Unix).
                tmp = Path(tempfile.gettempdir()).as_posix()
                # Guard: MSYS/Git Bash may return /tmp which is not absolute on Windows.
                # Use os.path.isabs() instead of string-matching /tmp — catches all
                # non-absolute paths regardless of the specific MSYS override value.
                # Per Python docs, gettempdir() resolves: TMPDIR → TEMP → TMP →
                # platform-specific → CWD. MSYS overrides TEMP/TMP to /tmp.
                if not _is_dispatcher_absolute(tmp):
                    # Try Windows-native TEMP/TMP env vars first
                    win_tmp = os.environ.get("TEMP") or os.environ.get("TMP") or ""
                    if win_tmp and os.path.isabs(win_tmp):
                        tmp = Path(win_tmp).as_posix()
                    else:
                        # Final fallback: Path.home() is always absolute on all platforms
                        tmp = (Path.home() / "tmp").as_posix()
                workspace = f"worktree:{tmp}/wt-{plan_id}-{run_ts}-{card_key}" if run_ts else f"worktree:{tmp}/wt-{plan_id}-{card_key}"
            branch = card.get("branch") or f"kanban/{plan_id}/{card_key}"
            cmd.extend(["--workspace", workspace])
            cmd.extend(["--branch", branch])
            cmd.extend(["--max-retries", str(max_retries_for_card(card))])

        # Read body from temp file, pass inline (--body-file not supported in all Hermes versions)
        with open(tmpfile, 'r', encoding="utf-8") as bf:
            body_content = bf.read()
        cmd.extend(["--body", body_content])
        cmd.append("--json")

        body_bytes = len(body_content.encode("utf-8"))
        timeout = create_card_timeout_seconds(body_content)
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()

        task_id = parse_create_task_id(out)
        if not task_id:
            print(
                f"  ERROR: create failed for {card.get('key', title)} "
                f"(body_bytes={body_bytes}, rc={result.returncode})",
                file=sys.stderr,
            )
            if out:
                print(f"  stdout: {out[:500]}", file=sys.stderr)
            if err:
                print(f"  stderr: {err[:500]}", file=sys.stderr)
            return None

        # Block immediately to beat the dispatcher (claims 'ready' cards in <1s).
        if block_after:
            import time as _time
            block_reason = "Awaiting dependency gate (auto_unblock when parents done)"
            blocked = False
            for attempt in range(1, 4):
                _, b_err, b_rc = hermes("kanban", "block", task_id, block_reason)
                if b_rc == 0:
                    # Verify the card is actually blocked
                    show_out, _, show_rc = hermes("kanban", "show", task_id)
                    if show_rc == 0 and "status:    blocked" in show_out:
                        blocked = True
                        break
                    else:
                        print(f"  WARN: block {task_id} reported success but status not 'blocked' (attempt {attempt}/3)", file=sys.stderr)
                else:
                    print(f"  WARN: block {task_id} failed (attempt {attempt}/3): {b_err[:200]}", file=sys.stderr)
                if attempt < 3:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    print(f"  RETRY: block {task_id} in {backoff}s (attempt {attempt + 1}/3)", file=sys.stderr)
                    _time.sleep(backoff)
            if not blocked:
                print(f"  ERROR: block {task_id} failed after 3 attempts — card creation aborted", file=sys.stderr)
                print(f"  ERROR: block manually: hermes kanban block {task_id}", file=sys.stderr)
                return None
        return task_id
    finally:
        os.unlink(tmpfile)


def link_cards(parent_id: str, child_id: str, dry_run: bool = False) -> bool:
    """Link parent → child dependency."""
    if dry_run:
        print(f"  [DRY-RUN] Would link: {parent_id} -> {child_id}")
        return True
    out, err, rc = hermes("kanban", "link", parent_id, child_id)
    return rc == 0


def find_existing_plan_cards(plan_id: str, card_keys: list[str]) -> dict[str, str]:
    """Return existing task IDs keyed by card key when plan_id already has cards on board."""
    if not plan_id:
        return {}
    out, _, rc = hermes("kanban", "list")
    if rc != 0:
        return {}
    existing: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("t_"):
            continue
        tid = parts[0]
        detail, _, _ = hermes("kanban", "show", tid)
        if f"plan_id: {plan_id}" not in detail and f"plan_id:{plan_id}" not in detail.replace(" ", ""):
            continue
        for key in card_keys:
            marker = f"card_key: {key}"
            if marker in detail or f"#### Card {key}" in detail or f"key: {key}" in detail:
                existing[key] = tid
                break
    return existing


def archive_prior_plan_cards(plan_id: str) -> tuple[bool, str, list[str]]:
    """Archive all non-running cards for plan_id. Refuse when any card is running."""
    if not plan_id:
        return True, "", []
    out, _, rc = hermes("kanban", "list")
    if rc != 0:
        return False, "hermes kanban list failed", []
    running: list[str] = []
    to_archive: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("t_"):
            continue
        tid = parts[0]
        detail, _, _ = hermes("kanban", "show", tid)
        if f"plan_id: {plan_id}" not in detail and f"plan_id:{plan_id}" not in detail.replace(" ", ""):
            continue
        status = ""
        for row in detail.splitlines():
            if row.strip().startswith("status:"):
                status = row.split(":", 1)[1].strip().lower()
                break
        if status == "running":
            running.append(tid)
        else:
            to_archive.append(tid)
    if running:
        return (
            False,
            f"Cannot archive-prior: running card(s) for {plan_id}: {', '.join(running)}",
            [],
        )
    archived: list[str] = []
    for tid in to_archive:
        _, err, arc = hermes("kanban", "archive", tid)
        if arc != 0:
            return False, f"archive {tid} failed: {err[:200]}", archived
        archived.append(tid)
    return True, f"Archived {len(archived)} card(s) for {plan_id}", archived


def verify_links(card_map: dict[str, str], cards: list[dict]) -> list[str]:
    """Verify all declared dependencies have corresponding links."""
    errors = []
    for card in cards:
        card_id = card_map.get(card["key"])
        if not card_id:
            continue
        # Check that all declared parents exist in card_map
        for parent_key in [card.get("wave_parent"), card.get("ordinal_parent")]:
            if parent_key and parent_key not in card_map:
                errors.append(f"{card['key']}: parent '{parent_key}' not found in card map")
    return errors


# ── Overlay profile resolution ─────────────────────────────────────────────

def _find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    overlay_rel = Path(".hermes") / "kanban-overrides" / "kanban-config.yaml"
    for parent in [start, *start.parents]:
        if (parent / overlay_rel).is_file():
            return parent
        if (parent / ".git").exists():
            return parent
    return start


def _read_overlay(project_root: Path) -> dict[str, str]:
    path = project_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if not path.is_file():
        return {}
    config: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            config[key.strip()] = val.strip().strip('"').strip("'")
    return config


def _resolve_dispatch_profiles(project_root: Path) -> tuple[str, str]:
    overlay = _read_overlay(project_root)
    worker = overlay.get("worker_profile", "kanban-advanced-worker")
    orchestrator = overlay.get("orchestrator_profile", "kanban-advanced-orchestrator")
    if worker == "worker":
        worker = "kanban-advanced-worker"
    if orchestrator == "orchestrator":
        orchestrator = "kanban-advanced-orchestrator"
    return worker, orchestrator


def _normalize_card_assignee(card: dict, worker: str, orchestrator: str) -> None:
    assignee = card.get("assignee")
    card_type = card.get("type", "code-gen")
    if assignee in ("worker", worker) or (not assignee and card_type == "code-gen"):
        card["assignee"] = worker
    elif assignee in ("orchestrator", orchestrator) or card_type in (
        "root", "gate", "audit", "manual", "verification-deploy"
    ):
        card["assignee"] = orchestrator
    elif not assignee:
        card["assignee"] = worker


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Validate input file
    input_path = args.cards_yaml or args.plan
    if not os.path.exists(input_path):
        sys.exit(f"ERROR: File not found: {input_path}")

    hermes_home = os.environ.get("HERMES_HOME", "")
    if not hermes_home:
        print("WARN: HERMES_HOME not set — cron scripts may not resolve", file=sys.stderr)

    project_root = _find_project_root(Path(input_path).resolve().parent)
    worker_profile, orchestrator_profile = _resolve_dispatch_profiles(project_root)

    # Generate run timestamp once for all cards — prevents same-plan_id concurrent-run collisions
    import datetime
    run_ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')

    plan_file_rel = ""
    if args.plan:
        try:
            plan_file_rel = Path(args.plan).resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            plan_file_rel = str(args.plan)

    # Parse plan
    if args.cards_yaml:
        print(f"Parsing cards YAML: {args.cards_yaml}")
        parsed = parse_yaml_cards(args.cards_yaml)
    else:
        print(f"Parsing plan: {args.plan}")
        parsed = parse_plan(args.plan)
    all_cards = parsed["cards"]
    for card in all_cards:
        _normalize_card_assignee(card, worker_profile, orchestrator_profile)

    plan_id = parsed.get("plan_id", "")

    # Capture wave baseline SHA before card generation (used by stamps + root card)
    head_sha = ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(Path.cwd()),
            timeout=10,
        )
        if r.returncode == 0:
            head_sha = r.stdout.strip()
    except Exception:
        pass

    stamp_all_impl_cards(
        all_cards,
        plan_id=plan_id,
        plan_file_rel=plan_file_rel,
        plan_path=args.plan if args.plan else None,
        wave_baseline=head_sha,
    )

    if args.plan:
        from lib.plan_parse import integration_verify_warnings, load_plan_text  # noqa: E402

        plan_text = load_plan_text(args.plan)
        for warning in integration_verify_warnings(all_cards, plan_text):
            print(f"WARN: {warning}", file=sys.stderr)
        from lib.card_body_fidelity import (  # noqa: E402
            _fmt_violation,
            validate_parsed_cards,
        )

        fidelity = validate_parsed_cards(
            plan_path=Path(args.plan),
            plan_text=plan_text,
            cards=all_cards,
            repo_root=project_root,
            plan_id=plan_id,
            profile="advisory" if args.dry_run else "balanced",
        )
        for v in fidelity:
            print(_fmt_violation(v), file=sys.stderr)
        if not args.dry_run and any(v.severity == "block" for v in fidelity):
            sys.exit(1)
    for card in all_cards:
        if plan_file_rel and "plan_file:" not in card.get("body", ""):
            card["body"] = f"plan_file: {plan_file_rel}\ncard_key: {card.get('key', '')}\n{card['body']}"

    impl_cards = [c for c in all_cards if c["type"] not in ("gate", "root", "audit")]

    if not args.dry_run and plan_id:
        dupes = find_existing_plan_cards(plan_id, [c["key"] for c in impl_cards])
        if dupes:
            if args.archive_prior:
                ok, msg, archived = archive_prior_plan_cards(plan_id)
                print(msg, file=sys.stderr)
                if not ok:
                    print(f"ERROR: {msg}", file=sys.stderr)
                    sys.exit(7)
                dupes = find_existing_plan_cards(plan_id, [c["key"] for c in impl_cards])
            if dupes:
                print(
                    f"ERROR: plan_id '{plan_id}' already has cards on board: "
                    + ", ".join(f"{k}={v}" for k, v in sorted(dupes.items())),
                    file=sys.stderr,
                )
                print(
                    "Archive the prior board, pass --archive-prior, or pass --gate-id to reuse the gate. "
                    "Do not decompose twice without archiving.",
                    file=sys.stderr,
                )
                sys.exit(7)

    # Auto-generate gate card (every board needs one)
    gate_card = {
        "key": "gate",
        "title": f"Gate — {parsed.get('plan_id', 'kanban plan')}",
        "type": "gate",
        "assignee": orchestrator_profile,
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 0,
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": f"plan_id: {parsed.get('plan_id', 'unknown')}\nGate card. All implementation cards link to gate. Unblock triggers wave 1 promotion.",
        "agent_body": None,
    }

    # Auto-generate root card
    root_card = {
        "key": "root",
        "title": f"{parsed.get('plan_id', 'Kanban plan')} — ROOT",
        "type": "root",
        "assignee": orchestrator_profile,
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 0,
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": f"plan_id: {parsed.get('plan_id', 'unknown')}\nWave-baseline: {head_sha}\nRoot card for {len(impl_cards)} implementation cards.\nCard total: {len(impl_cards)} (code-gen) + 1 gate + 1 audit + 1 root = {len(impl_cards) + 3}",
        "agent_body": None,
    }

    # Auto-generate audit card
    baseline_line = f"Audit-baseline-sha: {head_sha}\n" if head_sha else ""
    audit_card = {
        "key": "audit",
        "title": f"Final audit — {parsed.get('plan_id', 'kanban plan')}",
        "type": "audit",
        "assignee": orchestrator_profile,
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 999,  # last wave
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": (
            f"plan_id: {parsed.get('plan_id', 'unknown')}\n"
            f"Type: audit\n"
            f"{baseline_line}"
            f"Final audit — run `python3 hermes-kanban-advanced-workflow/scripts/final_audit_sanity.py "
            f"--plan-id {parsed.get('plan_id', 'unknown')} --tier all` (Tier 1 plan-scope + Tier 2 doc coverage). "
            f"On violations: `--spawn-remediation`. See plugin/data/references/final-audit-sanity-check.md."
        ),
        "agent_body": None,
    }

    # Rebuild card list with gate first, then impl, then audit
    all_cards = [gate_card] + impl_cards + [root_card, audit_card]

    # Separate cards by type
    gate_cards = [c for c in all_cards if c["type"] == "gate"]
    root_cards = [c for c in all_cards if c["type"] == "root"]
    audit_cards = [c for c in all_cards if c["type"] == "audit"]
    # impl_cards already computed above

    if not gate_cards:
        sys.exit("ERROR: No gate card generated")
    gate_card = gate_cards[0]

    print(f"\nPlan: {len(all_cards)} cards ({len(impl_cards)} impl, {len(gate_cards)} gate, {len(root_cards)} root)")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}\n")

    # ── Step 1: Gate card ──────────────────────────────────────────────────
    print("=== Step 1: Gate card (create → block) ===")
    if args.gate_id:
        # Orchestrator SOP already created and blocked the gate — reuse it.
        gate_id = args.gate_id
        print(f"  Gate: {gate_id} (reusing existing — skipping auto-create)")
    else:
        gate_id = create_card(gate_card, args.dry_run, block_after=True, run_ts=run_ts)
        if not gate_id:
            sys.exit("ERROR: Failed to create gate card")
        print(f"  Gate: {gate_id} (blocked — orchestrator-only control card)")
    time.sleep(args.stagger_ms / 1000)

    # ── Step 2: Create implementation cards (blocked on create) ──
    print(f"\n=== Step 2: {len(impl_cards)} implementation cards (create → block) ===")
    card_ids: dict[str, str] = {"gate": gate_id}

    created = 1  # gate counts as 1
    for card in impl_cards:
        cid = create_card(card, args.dry_run, block_after=True, run_ts=run_ts)
        if not cid:
            sys.exit(f"ERROR: Failed to create implementation card {card['key']}")
        card_ids[card["key"]] = cid
        print(f"  {card['key']}: {cid} (blocked)")
        created += 1
        time.sleep(args.stagger_ms / 1000)
        if created % args.pause_every == 0:
            print(f"  --- pausing {args.pause_ms}ms ---")
            time.sleep(args.pause_ms / 1000)

    # Also create root card if present (not blocked — completed below)
    for root_card in root_cards:
        rid = create_card(root_card, args.dry_run, block_after=False, run_ts=run_ts)
        if rid:
            card_ids[root_card["key"]] = rid
            print(f"  {root_card['key']}: {rid} (root)")
        time.sleep(args.stagger_ms / 1000)

    # Also create audit card (blocked on create — gates on all impl cards)
    for audit in audit_cards:
        aid = create_card(audit, args.dry_run, block_after=True, run_ts=run_ts)
        if aid:
            card_ids[audit["key"]] = aid
            print(f"  audit: {aid} (blocked)")
        time.sleep(args.stagger_ms / 1000)

    # ── Step 3: Link dependencies ──
    print(f"\n=== Step 3: Link dependencies ===")
    links_created = 0
    seen_links = set()  # deduplicate (card2 parent of card8 for both wave + ordinal)
    for card in impl_cards:
        child_id = card_ids.get(card["key"])
        if not child_id:
            continue

        # 3a: Link to gate — only for first card in wave chain (no wave_parent).
        # Linking all cards to gate causes Hermes to promote them all when gate
        # completes, bypassing the serial wave_parent chain.
        if not card.get("wave_parent"):
            link_key = f"gate->{card['key']}"
            if card["key"] != "gate" and gate_id and link_key not in seen_links:
                if link_cards(gate_id, child_id, args.dry_run):
                    seen_links.add(link_key)
                    links_created += 1
                    if not args.dry_run:
                        print(f"  gate -> {card['key']}")

        # 3b: Link to wave parent
        wp = card.get("wave_parent")
        if wp and wp in card_ids:
            link_key = f"{wp}->{card['key']}"
            if link_key not in seen_links:
                if link_cards(card_ids[wp], child_id, args.dry_run):
                    seen_links.add(link_key)
                    links_created += 1
                    if not args.dry_run:
                        print(f"  {wp} (wave) -> {card['key']}")

        # 3c: Link to ordinal parent
        op = card.get("ordinal_parent")
        if op and op in card_ids:
            link_key = f"{op}->{card['key']}"
            if link_key not in seen_links:
                if link_cards(card_ids[op], child_id, args.dry_run):
                    seen_links.add(link_key)
                    links_created += 1
                    if not args.dry_run:
                        print(f"  {op} (ordinal) -> {card['key']}")

    print(f"  Total links: {links_created}")

    # Link audit card to all impl cards (audit gates on all implementation)
    audit_id = card_ids.get("audit")
    if audit_id:
        for card in impl_cards:
            child_id = card_ids.get(card["key"])
            if child_id:
                link_key = f"audit->{card['key']}"
                if link_key not in seen_links:
                    if link_cards(child_id, audit_id, args.dry_run):
                        seen_links.add(link_key)
                        links_created += 1
        # audit was already blocked on create; auto_unblock releases it once
        # every implementation parent is done.

    # Cap verification card parents to max 2 (gate + last impl card).
    # Verification cards only need to gate on the gate and their immediate
    # predecessor — not all siblings. This prevents triple-parent situations
    # from remediation or wave-chain edge cases.
    for card in impl_cards:
        if card.get("type", "").startswith("verification"):
            child_id = card_ids.get(card["key"])
            if not child_id:
                continue
            # Determine which parent links to keep: gate + highest-ordinal impl parent
            keep_parents = set()
            if gate_id:
                keep_parents.add(gate_id)
            # Find the highest-ordinal impl parent from wave_parent or ordinal_parent
            impl_parent = card.get("wave_parent") or card.get("ordinal_parent")
            if impl_parent and impl_parent in card_ids:
                keep_parents.add(card_ids[impl_parent])
            # Remove any impl→verification links not in the keep set
            # (audit links are impl→audit, not affected)
            for other_card in impl_cards:
                if other_card["key"] == card["key"]:
                    continue
                other_id = card_ids.get(other_card["key"])
                if other_id and other_id not in keep_parents:
                    # Check if this link exists and remove it
                    link_key = f"{other_card['key']}->{card['key']}"
                    if link_key in seen_links:
                        # Unlink via hermes kanban unlink if not dry-run
                        if not args.dry_run:
                            hermes("kanban", "unlink", other_id, child_id)
                        seen_links.discard(link_key)
                        links_created -= 1
                        print(f"  unlinked excess parent: {other_card['key']} -> {card['key']} (verification cap)")

    # Complete root card immediately
    root_id = card_ids.get("root")
    if root_id and not args.dry_run:
        hermes("kanban", "complete", root_id, "--summary", f"Root complete — {len(impl_cards)} cards dispatched.")
        print(f"  root completed")

    # ── Step 4: Verify dependencies ──
    print(f"\n=== Step 4: Verify dependencies ===")
    errors = verify_links(card_ids, impl_cards)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit("Dependency verification failed — fix plan and retry")
    print("  All dependencies verified")

    # ── Step 5: Orchestrator next-steps ──
    print(f"\n=== Step 5: Orchestrator instructions ===")
    print(f"  Gate {gate_id} is blocked. Board is ready for validation.")
    print(f"")
    print(f"  Next steps (orchestrator profile only):")
    print(f"    1. Run validate_board.sh to confirm all cards and links are correct")
    print(f"    2. hermes kanban complete {gate_id} --summary \"Board validated. Releasing wave 1.\"")
    print(f"    3. The dispatcher promotes wave-1 todo cards to ready automatically.")
    print(f"")
    print(f"  Do NOT unblock the gate — complete it. Completing triggers wave promotion.")

    # ── Step 6: Cron health (check by default; create only with --provision-crons) ──
    plan_id_for_cron = parsed.get("plan_id", "")
    if not plan_id_for_cron and args.plan:
        plan_id_for_cron = Path(args.plan).stem.replace(".plan", "")
    if not args.no_crons:
        cron_script = Path(__file__).resolve().parent / "provision_kanban_crons.sh"
        if args.provision_crons:
            print(f"\n=== Step 6: Create auto-unblock + board-keeper crons ===")
            cron_cmd = ["bash", str(cron_script), "--create"]
            if plan_id_for_cron:
                cron_cmd.extend(["--plan-id", plan_id_for_cron])
            if args.dry_run:
                cron_cmd.append("--dry-run")
        else:
            print(f"\n=== Step 6: Verify wave crons (pre-provisioned at handoff) ===")
            cron_cmd = ["bash", str(cron_script), "--check"]
        result = subprocess.run(cron_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0 and not args.dry_run:
            if args.provision_crons:
                sys.exit("Cron provisioning failed — fix gateway/hermes cron and retry")
            sys.exit(
                "Wave crons check failed — default profile must run kanban_handoff.py "
                "(provisions crons) or re-run: provision_kanban_crons.sh --create --check"
            )

    # ── Output ──
    print(f"\n=== Summary ===")
    print(f"  Gate: {gate_id} (blocked — complete to release wave 1)")
    print(f"  Cards: {len(card_ids) - 1}")
    if plan_id_for_cron and not args.dry_run:
        update_plan_memory(
            args.plan or args.cards_yaml or "",
            plan_id_for_cron,
            len(impl_cards),
            {k: v for k, v in card_ids.items() if k not in ("gate", "root", "audit")},
        )
        # Also register orchestrator cards (handoff, gate, root, audit)
        # so generate_postmortem.py counts all tasks, not just impl cards.
        all_task_ids = {
            "handoff": os.environ.get("HERMES_KANBAN_TASK", ""),
            "gate": gate_id,
            "root": card_ids.get("root", ""),
            "audit": card_ids.get("audit", ""),
        }
        orchestrator_ids = {k: v for k, v in all_task_ids.items() if v}
        if orchestrator_ids:
            import json
            mem = repo_root / ".hermes" / "kanban" / "memory" / f"{plan_id_for_cron}.json"
            if mem.exists():
                data = json.loads(mem.read_text())
                data.setdefault("orchestrator_task_ids", {}).update(orchestrator_ids)
                mem.write_text(json.dumps(data, indent=2))
        try:
            from lib.orchestrator_token_checkpoint import maybe_log_orchestrator_checkpoint  # noqa: E402

            maybe_log_orchestrator_checkpoint(
                plan_id_for_cron,
                "decompose-complete",
                note=f"{len(impl_cards)} impl cards",
            )
        except Exception:
            pass
    if args.json:
        print(json.dumps({"gate": gate_id, "cards": card_ids}, indent=2))
    else:
        for key, cid in sorted(card_ids.items()):
            if key != "gate":
                print(f"  {key}: {cid}")


if __name__ == "__main__":
    main()
