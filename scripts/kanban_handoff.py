#!/usr/bin/env python3
"""
kanban_handoff.py — Board-mediated orchestrator handoff card builder.

When a non-orchestrator profile is told to "execute the plan", it cannot create
governed cards itself (the dispatcher matches a card's ``assignee`` to a profile
name, and only the orchestrator profile may run decomposition). Instead of asking
the user to start a new session under the orchestrator profile, this script
creates ONE hardened handoff card assigned to the orchestrator profile. The
gateway dispatcher claims that ``ready`` card and spawns an orchestrator-profile
agent, which runs the decomposition SOP autonomously.

Hardening (this card is meant to be as bulletproof as possible):

  * SOP-ONLY body — NO ``agent -p`` fenced block. A coding ``agent`` block would
    make Hermes treat the card as a triage/work card and (with auto_decompose on)
    LLM-decompose it into stub children. The orchestrator agent reads the SOP from
    the body and runs it via its terminal.
  * Deterministic title ``Decompose: <plan_id>`` + ``Type: orchestrator-handoff``
    marker line — used for idempotency scans and the governance carve-out.
  * Idempotent — refuses to create a second handoff card while an open one
    (todo/ready/running/blocked) already exists for the same plan_id; also passes
    ``--idempotency-key`` so Hermes itself dedups.
  * Preconditions (fail fast, clear messages): orchestrator profile exists, the
    in-gateway dispatcher is enabled, ``kanban.auto_decompose`` is false, and the
    gateway is running. Never create a card that would silently sit stuck.

Usage:
    python3 kanban_handoff.py --plan <plan.md> [--plan-id <id>] [--dry-run]
                              [--allow-offline] [--json]

Exit codes:
    0  card created or reused (idempotent hit)
    2  orchestrator profile missing
    3  gateway not running (unless --allow-offline)
    4  dispatcher disabled / auto_decompose enabled (unless --allow-offline)
    5  plan file not found / plan_id could not be determined
    6  card creation failed
    7  board not clean (existing plan cards — archive after operator confirms, or --force)
    8  cron provisioning failed (provision_kanban_crons --create/--check)

Cron jobs are provisioned in the **default profile session** (this script) before the
handoff card is created — not by the orchestrator agent. Orchestrator runbook verifies
only (`--check`), with idempotent `--create` fallback when check fails.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HANDOFF_TYPE = "orchestrator-handoff"
OPEN_STATUSES = frozenset({"todo", "ready", "running", "blocked"})


# ── Config resolution (self-contained; mirrors plugin/config_overlay.py) ─────

def _find_project_root(start: Path | None = None) -> Path:
    for env_name in ("KANBAN_PROJECT_ROOT", "HERMES_PROJECT_ROOT"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    start = (start or Path.cwd()).resolve()
    overlay_rel = Path(".hermes") / "kanban-overrides" / "kanban-config.yaml"
    config_hit = git_hit = None
    for parent in [start, *start.parents]:
        if (parent / overlay_rel).is_file() and config_hit is None:
            config_hit = parent
        if (parent / ".git").exists() and git_hit is None:
            git_hit = parent
    return config_hit or git_hit or start


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


def _overlay_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    s = str(value).strip().lower()
    if s in ("false", "0", "no", "off"):
        return False
    if s in ("true", "1", "yes", "on"):
        return True
    return default


def _resolve_notification_overlay(
    project_root: Path, overlay: dict[str, str]
) -> dict[str, str]:
    """Snapshot notify_lifecycle / walk_away_mode / deliver for handoff stamp."""
    notify_lifecycle = _overlay_bool(
        overlay.get("notify_lifecycle"), default=True
    )
    walk_away_mode = _overlay_bool(
        overlay.get("walk_away_mode")
        or overlay.get("notify_on_complete"),
        default=False,
    )
    deliver = "unknown"
    lib_dir = Path(__file__).resolve().parent / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    try:
        from hermes_notify_deliver import resolve_notify_deliver  # type: ignore

        deliver = resolve_notify_deliver(project_root)
    except Exception:
        pass
    return {
        "notify_lifecycle": "true" if notify_lifecycle else "false",
        "walk_away_mode": "true" if walk_away_mode else "false",
        "notify_deliver_resolved": deliver,
    }


def _run_cron_provision(
    plan_id: str,
    bundle_root: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
) -> tuple[str, bool, str]:
    """Run provision_kanban_crons --create then --check in default-profile session."""
    cron_script = bundle_root / "scripts" / "provision_kanban_crons.sh"
    if not cron_script.is_file():
        cron_script = project_root / "scripts" / "provision_kanban_crons.sh"
    if not cron_script.is_file():
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"FAILED at {ts}: provision_kanban_crons.sh not found", False, "script missing"

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bash_cron = _bash_path(cron_script)
    # shell=True is required on Windows so the spawned bash process inherits
    # MSYS2 path translation. Passing bash + args as a list bypasses the
    # shell layer and MSYS2's automount can't resolve /c/ paths.
    create_args = f"bash {bash_cron} --create --plan-id {plan_id}"
    if dry_run:
        create_args += " --dry-run"

    try:
        create = subprocess.run(
            create_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=str(project_root),
            shell=True,
        )
        if create.returncode != 0 and not dry_run:
            detail = (create.stdout + create.stderr).strip()[:400]
            return f"FAILED at {ts}: create exit {create.returncode}", False, detail

        check = subprocess.run(
            f"bash {bash_cron} --check",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(project_root),
            shell=True,
        )
        if check.returncode != 0 and not dry_run:
            detail = (check.stdout + check.stderr).strip()[:400]
            return f"FAILED at {ts}: check exit {check.returncode}", False, detail

        mode = "dry-run" if dry_run else "PASSED"
        return f"{mode} at {ts}", True, (check.stdout or create.stdout).strip()[:200]
    except subprocess.TimeoutExpired:
        return f"FAILED at {ts}: cron provision timed out", False, "timeout"
    except Exception as exc:
        return f"FAILED at {ts}: {exc}", False, str(exc)


def _bundle_has_scripts(root: Path) -> bool:
    return (root / "scripts" / "coding_agent_invoke.sh").is_file()


def _bash_path(path: Path) -> str:
    """Return a path Git Bash can execute on Windows (MSYS path conversion)."""
    resolved = path.resolve()
    posix = resolved.as_posix()
    if os.name == "nt" and len(posix) >= 2 and posix[1] == ":":
        return f"/{posix[0].lower()}{posix[2:]}"
    return posix


def _parse_subagent_gate_enabled_from_text(text: str) -> bool | None:
    """Return enabled flag when subagent_gate block is present; else None (default true)."""
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("subagent_gate:"):
            in_block = True
            continue
        if in_block:
            if ":" in stripped and not line[:1].isspace():
                break
            if stripped.startswith("enabled:"):
                val = stripped.split(":", 1)[1].strip().strip('"').strip("'").lower()
                return val in ("true", "1", "yes", "on")
    return None


def _resolve_subagent_gate_enabled(project_root: Path, overlay: dict[str, str]) -> bool:
    """Mirror plugin/config_overlay.resolve_subagent_gate_enabled (default true)."""
    raw = overlay.get("subagent_gate_enabled", "").strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    if raw in ("true", "1", "yes", "on"):
        return True
    config_path = project_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if config_path.is_file():
        parsed = _parse_subagent_gate_enabled_from_text(
            config_path.read_text(encoding="utf-8")
        )
        if parsed is not None:
            return parsed
    return True


def _resolve_bundle_root(project_root: Path, overlay: dict[str, str]) -> Path | None:
    """Mirror scripts/lib/kanban_bundle.sh _resolve_kanban_bundle_root order."""
    if _bundle_has_scripts(project_root):
        return project_root.resolve()

    bundle_path = overlay.get("bundle_path", "").strip()
    if bundle_path:
        candidate = Path(bundle_path)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if _bundle_has_scripts(candidate):
            return candidate

    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    workflow_dir = os.environ.get("KANBAN_WORKFLOW_DIR", "").strip()
    for candidate_str in (
        workflow_dir,
        f"{hermes_home}/plugins/kanban-advanced" if hermes_home else "",
        str(project_root / "hermes-kanban-advanced-workflow"),
        str(project_root / ".hermes" / "plugins" / "kanban-advanced"),
    ):
        if not candidate_str:
            continue
        candidate = Path(candidate_str).expanduser().resolve()
        if _bundle_has_scripts(candidate):
            return candidate
    return None


def _resolve_gate_script(project_root: Path, overlay: dict[str, str]) -> Path | None:
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    candidates: list[Path] = []
    if hermes_home:
        candidates.append(Path(hermes_home) / "scripts" / "pre_dispatch_gate.sh")
    bundle = _resolve_bundle_root(project_root, overlay)
    if bundle:
        candidates.append(bundle / "scripts" / "pre_dispatch_gate.sh")
    candidates.append(project_root / "scripts" / "pre_dispatch_gate.sh")
    candidates.append(
        project_root / ".hermes" / "plugins" / "kanban-advanced" / "scripts" / "pre_dispatch_gate.sh"
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _discover_cards_yaml(
    plan_id: str,
    plan_path: Path,
    project_root: Path,
    overlay: dict[str, str],
) -> Path | None:
    plan_memory = overlay.get("plan_memory_path", ".hermes/kanban/memory").strip()
    candidates = [
        plan_path.parent / f"{plan_id}.yaml",
        plan_path.with_suffix(".yaml"),
        project_root / plan_memory / f"{plan_id}.yaml",
        project_root / ".hermes" / "kanban" / "memory" / f"{plan_id}.yaml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


# ── hermes CLI helpers ───────────────────────────────────────────────────────

def _hermes(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    # Force UTF-8 decoding: hermes prints non-ASCII (table glyphs, em dashes) that
    # crash the default cp1252 reader on Windows.
    expanded = list(args)
    if expanded and expanded[0] == "kanban" and (len(expanded) < 2 or expanded[1] != "boards"):
        board = os.environ.get("HERMES_KANBAN_BOARD", "").strip()
        if board and board != "default":
            expanded = ["kanban", "--board", board, *expanded[1:]]
    return subprocess.run(
        ["hermes", *expanded],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _config_path() -> Path | None:
    """Resolve the active config.yaml path from `hermes config show`."""
    try:
        out = _hermes("config", "show").stdout
    except Exception:
        return None
    m = re.search(r"Config:\s*(.+)", out)
    if m:
        candidate = Path(m.group(1).strip())
        if candidate.is_file():
            return candidate
    return None


def _kanban_settings() -> dict[str, bool]:
    """Read kanban.dispatch_in_gateway and kanban.auto_decompose from config.yaml.

    Returns a dict with keys 'dispatch_in_gateway' and 'auto_decompose'. Missing
    keys default to Hermes defaults (dispatch_in_gateway=True, auto_decompose=True)
    so the precondition check errs on the side of surfacing a problem.
    """
    settings = {"dispatch_in_gateway": True, "auto_decompose": True}
    path = _config_path()
    if not path:
        return settings
    text = path.read_text(encoding="utf-8")
    # Prefer a real YAML parse when available; fall back to targeted regex.
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        kb = data.get("kanban", {}) if isinstance(data, dict) else {}
        if isinstance(kb, dict):
            settings["dispatch_in_gateway"] = bool(
                kb.get("dispatch_in_gateway", True)
            )
            settings["auto_decompose"] = bool(kb.get("auto_decompose", True))
            return settings
    except Exception:
        pass
    for key in ("dispatch_in_gateway", "auto_decompose"):
        m = re.search(rf"^\s*{key}:\s*(\S+)", text, flags=re.MULTILINE)
        if m:
            settings[key] = m.group(1).strip().lower() in {"true", "yes", "1"}
    return settings


def _orchestrator_profile_exists(profile: str) -> bool:
    try:
        out = _hermes("profile", "list").stdout
    except Exception:
        return False
    # Profile names are whitespace-delimited tokens in the table body.
    return bool(re.search(rf"(?m)^\s*\W?\s*{re.escape(profile)}\b", out)) or (
        profile in out.split()
    )


def _gateway_running() -> bool:
    try:
        r = _hermes("gateway", "status")
    except Exception:
        return False
    return r.returncode == 0 and "running" in r.stdout.lower()


def _parse_gate_result(stdout: str, stderr: str) -> tuple[int, int] | None:
    combined = (stdout or "") + (stderr or "")
    m = re.search(r"\[GATE\] Result:\s*(\d+)\s+failures,\s*(\d+)\s+warnings", combined)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_gate_failed_checks(stdout: str, stderr: str) -> list[str]:
    """Return check names that printed FAIL (not WARN)."""
    combined = (stdout or "") + (stderr or "")
    failed: list[str] = []
    for line in combined.splitlines():
        m = re.match(r"\[GATE\]\s+(.+?)\s+\.\.\.\s+FAIL", line.strip())
        if m:
            failed.append(m.group(1).strip())
    return failed


_CODING_AGENT_CLI_SKIP_HINT = (
    " If the coding-agent CLI check is blocking, export "
    "PREFLIGHT_SKIP_CODING_AGENT_CLI=1 and retry."
)
_CODING_AGENT_LOCK_HINT = (
    " Stale auth lock? rm -f ${HERMES_HOME:-~/.hermes}/.locks/coding-agent-auth.lock"
)


def _gate_timeout_hint(message: str) -> str:
    lowered = message.lower()
    hints = []
    if "timeout" in lowered or "timed out" in lowered or "124" in lowered:
        hints.append(_CODING_AGENT_CLI_SKIP_HINT)
    if "coding_agent_cli" in lowered or "coding agent cli" in lowered:
        hints.append(_CODING_AGENT_CLI_SKIP_HINT)
    if "lock" in lowered or "flock" in lowered:
        hints.append(_CODING_AGENT_LOCK_HINT)
    return "".join(dict.fromkeys(hints))


def _run_pre_dispatch_gate(
    plan_id: str,
    repo_root: Path,
    overlay: dict[str, str],
) -> tuple[str, Path | None]:
    """Run pre_dispatch_gate.sh and return (status stamp, resolved script path).

    Returns PASSED stamp with failure/warning counts on rc=0, UNKNOWN if absent,
    or FAILED on non-zero exit. Never raises.
    """
    gate_script = _resolve_gate_script(repo_root, overlay)
    if gate_script is None:
        return "UNKNOWN (pre_dispatch_gate.sh not found)", None
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gate_path = _bash_path(gate_script)
    stamp_path = gate_script.resolve().as_posix()
    try:
        # shell=True is required on Windows so the spawned bash process inherits
        # MSYS2 path translation. Passing bash + args as a list bypasses the
        # shell layer and MSYS2's automount can't resolve /c/ paths, causing
        # "No such file or directory" even though the file exists.
        # PREFLIGHT_SKIP_CODING_AGENT_CLI prevents the preflight sub-check
        # from hanging on coding-agent auth probes in non-interactive contexts.
        env = {
            **os.environ,
            "PREFLIGHT_SKIP_CODING_AGENT_CLI": "1",
        }
        r = subprocess.run(
            f"bash {gate_path} {plan_id}",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=str(repo_root),
            shell=True,
            env=env,
        )
        if r.returncode == 0:
            counts = _parse_gate_result(r.stdout, r.stderr)
            if counts:
                failures, warnings = counts
                stamp = (
                    f"PASSED at {ts} ({failures} failures, {warnings} warnings) "
                    f"via {stamp_path}"
                )
            else:
                stamp = f"PASSED at {ts} via {stamp_path}"
            return stamp, gate_script
        summary = (r.stdout + r.stderr).strip().splitlines()
        failed_checks = _parse_gate_failed_checks(r.stdout, r.stderr)
        if failed_checks:
            reason = "failed: " + ", ".join(failed_checks[:8])
        else:
            reason = next((l for l in summary if l.strip()), "non-zero exit").strip()[:120]
        hint = _gate_timeout_hint(reason + " " + r.stdout + r.stderr)
        return f"FAILED at {ts}: {reason}{hint}", gate_script
    except subprocess.TimeoutExpired as exc:
        hint = _gate_timeout_hint(str(exc))
        return f"UNKNOWN (error: gate timed out after 120s){hint}", gate_script
    except Exception as exc:
        hint = _gate_timeout_hint(str(exc))
        return f"UNKNOWN (error: {exc}){hint}", gate_script


def _list_cards() -> list[dict]:
    """Return all board cards as dicts (best-effort JSON, fallback to text)."""
    try:
        r = _hermes("kanban", "list", "--json")
        if r.returncode == 0 and r.stdout.strip().startswith("["):
            return json.loads(r.stdout)
    except Exception:
        pass
    # Text fallback: parse "t_xxxxxxxx <status> ... <title>" rows loosely.
    cards: list[dict] = []
    try:
        out = _hermes("kanban", "list").stdout
    except Exception:
        return cards
    for line in out.splitlines():
        m = re.match(r"\s*(t_[a-zA-Z0-9]{8})\s+(\w+)\s+(.*)", line)
        if m:
            cards.append(
                {"id": m.group(1), "status": m.group(2), "title": m.group(3).strip()}
            )
    return cards


def _find_open_handoff(plan_id: str, title: str) -> str | None:
    for card in _list_cards():
        if not isinstance(card, dict):
            continue
        status = str(card.get("status", "")).lower()
        if status not in OPEN_STATUSES:
            continue
        ctitle = str(card.get("title", ""))
        cbody = str(card.get("body", ""))
        if ctitle == title or (
            HANDOFF_TYPE in cbody and f"plan_id: {plan_id}" in cbody
        ):
            return str(card.get("id", "")) or None
    return None


def _cards_for_plan(plan_id: str) -> list[dict]:
    """All board cards tied to plan_id (any status)."""
    matches: list[dict] = []
    needle = f"plan_id: {plan_id}"
    for card in _list_cards():
        if not isinstance(card, dict):
            continue
        body = str(card.get("body", ""))
        title = str(card.get("title", ""))
        if needle in body or plan_id in title:
            matches.append(card)
    return matches


def _check_board_cleanliness(
    plan_id: str,
    *,
    force: bool = False,
) -> tuple[bool, str, list[str]]:
    """Return (ok, message, archived_ids). Exit 7 when not ok and not force."""
    cards = _cards_for_plan(plan_id)
    if not cards:
        return True, "", []

    running = [
        c for c in cards if str(c.get("status", "")).lower() == "running"
    ]

    if force:
        archived: list[str] = []
        skipped: list[str] = []
        for card in cards:
            cid = str(card.get("id", "")).strip()
            if not cid:
                continue
            if str(card.get("status", "")).lower() == "running":
                skipped.append(cid)
                continue
            result = _hermes("kanban", "archive", cid)
            if result.returncode == 0:
                archived.append(cid)
            else:
                return (
                    False,
                    f"Failed to archive {cid}: {(result.stderr or result.stdout).strip()}",
                    archived,
                )
        msg_parts = [f"Archived {len(archived)} card(s) for plan_id {plan_id}."]
        if skipped:
            msg_parts.append(
                f"Skipped {len(skipped)} running card(s): {', '.join(skipped)}."
            )
        return True, " ".join(msg_parts), archived

    if running:
        ids = ", ".join(str(c.get("id", "?")) for c in running)
        return (
            False,
            (
                f"Board has {len(running)} running card(s) for plan_id {plan_id} "
                f"({ids}). Wind down to blocked or done before handoff."
            ),
            [],
        )

    lines = [
        f"Board has {len(cards)} existing card(s) for plan_id {plan_id}:",
    ]
    for card in cards:
        lines.append(
            f"  {card.get('id')} ({card.get('status')}): "
            f"{str(card.get('title', ''))[:80]}"
        )
    lines.extend(
        [
            "Confirm with the operator before archiving stale cards.",
            "Then run: hermes kanban archive <id> for each row above.",
            "Or re-run handoff with --force after operator approval "
            "(refused while any card is running).",
        ]
    )
    return False, "\n".join(lines), []


def _check_git_freshness(plan_id: str, project_root: Path) -> tuple[bool, str]:
    """Return (ok, message). Check for stale git branches/worktrees/attestation."""
    import subprocess, glob

    # Check for stale kanban branches
    result = subprocess.run(
        ["git", "branch"], capture_output=True, text=True, cwd=str(project_root)
    )
    stale_branches = [
        line.strip().lstrip("* ")
        for line in result.stdout.splitlines()
        if f"kanban/{plan_id}/" in line
    ]

    # Check for stale worktrees
    # Primary: check .worktrees/ via git (post-migration to Hermes convention)
    # Secondary (belt-and-suspenders): check temp dir for legacy worktrees
    import os
    tmp = os.environ.get("KANBAN_TEMP") or os.environ.get("TEMP") or "/tmp"
    wt_pattern = os.path.join(tmp, f"wt-{plan_id}-*")
    stale_worktrees = glob.glob(wt_pattern)
    # Also check .worktrees/ in repo
    repo_wt_pattern = str(project_root / ".worktrees" / f"wt-*")
    stale_worktrees.extend(glob.glob(repo_wt_pattern))

    # Check for stale attestation
    attestation = project_root / ".hermes" / "kanban" / f"attestation-{plan_id}.yaml"

    issues = []
    if stale_branches:
        issues.append(f"  git branches: {', '.join(stale_branches[:5])}")
    if stale_worktrees:
        issues.append(f"  worktrees: {', '.join(stale_worktrees[:5])}")
    if attestation.exists():
        issues.append(f"  attestation: {attestation}")

    if issues:
        return False, (
            f"Stale state from prior run detected for plan_id {plan_id}:\n"
            + "\n".join(issues)
            + f"\nRun: bash scripts/git_safe_cleanup.sh --clean --plan-id {plan_id}"
        )
    return True, ""


# ── Plan id + body ───────────────────────────────────────────────────────────

def _derive_plan_id(plan_path: Path, explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    try:
        text = plan_path.read_text(encoding="utf-8")
    except Exception:
        return None
    for key in ("plan_id", "plan"):
        m = re.search(rf"(?m)^\s*{key}:\s*(.+)$", text)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    stem = plan_path.stem
    return stem[: -len(".plan")] if stem.endswith(".plan") else stem


def _gateway_status_stamp() -> tuple[str, bool]:
    """Return (stamp line, dispatch_ok) from hermes gateway status."""
    try:
        r = _hermes("gateway", "status")
        text = (r.stdout or r.stderr or "").strip()
        running = r.returncode == 0 and "running" in text.lower()
        first = text.splitlines()[0][:120] if text else "no output"
        stamp = f"{'running' if running else 'not_running'} ({first})"
        return stamp, running
    except Exception as exc:
        return f"unknown ({exc})", False


def _gate_card_body(plan_id: str) -> str:
    """Match kanban_decompose.py gate card body (plan_id for lifecycle gate_done)."""
    return (
        f"plan_id: {plan_id}\n"
        "Gate card. All implementation cards link to gate. Unblock triggers wave 1 promotion."
    )





def _create_plan_board(plan_id: str) -> str:
    """Create a per-run kanban board with a timestamp suffix. Every handoff
    gets a fresh board — no stale cards from prior runs. Returns board slug."""
    import re as _re
    import datetime as _dt
    base = _re.sub(r'[^a-z0-9-]', '-', plan_id.lower())[:48].strip('-') or plan_id
    ts = _dt.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = f"{base}-{ts}"
    name = f"{plan_id} — {ts}"
    # Create board
    create = subprocess.run(
        ["hermes", "kanban", "boards", "create", slug, "--name", name],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15,
    )
    if create.returncode != 0:
        print(f"[kanban_handoff] WARNING: board creation failed, using default: {create.stderr.strip()}", file=sys.stderr)
        return "default"
    return slug


def _archive_prior_boards(plan_id: str) -> int:
    """Archive empty boards matching plan_id. Returns count archived."""
    base = re.sub(r'[^a-z0-9-]', '-', plan_id.lower())[:48].strip('-')
    if not base:
        return 0
    try:
        r = subprocess.run(
            ["hermes", "kanban", "boards", "list"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return 0
        count = 0
        for line in r.stdout.splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            slug = parts[0].lstrip('●▶⊘✓✗○◆◇').strip()
            if not slug.startswith(base):
                continue
            # Only archive if board appears empty
            if '(empty)' in line or '(no matching tasks)' in line:
                subprocess.run(
                    ["hermes", "kanban", "boards", "rm", slug],
                    capture_output=True, timeout=10
                )
                count += 1
        return count
    except Exception:
        return 0


def _archive_board(slug: str) -> bool:
    """Archive a kanban board by slug. Returns True on success."""
    if not slug or slug == "default":
        return False
    try:
        r = subprocess.run(
            ["hermes", "kanban", "boards", "rm", slug],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def _build_body(plan_id: str, plan_path: Path, repo_root: Path, working_branch: str,
                orchestrator_profile: str,
                bundle_root: Path,
                kanban_board: str = "default",
                cards_yaml_path: Path | None = None,
                gate_status: str = "UNKNOWN (not run)",
                gate_script: Path | None = None,
                gateway_at_handoff: str = "unknown",
                notification_overlay: dict[str, str] | None = None,
                cron_provision: str = "UNKNOWN (not run)") -> str:
    """SOP-only handoff body. NO ``agent -p`` block by design.

    Designed as a command-first runbook: literal CLI commands are pre-substituted
    so the orchestrator can execute without discovery overhead.  pre_dispatch_gate
    status is stamped at creation time so the orchestrator skips re-running it when
    already PASSED.
    """
    if cards_yaml_path and cards_yaml_path.is_file():
        decompose_source = f'--cards-yaml "{cards_yaml_path}"'
        source_note = f"(cards YAML — workspace/branch per card)"
    else:
        decompose_source = f'--plan "{plan_path}"'
        source_note = f"(plan markdown — workspace defaults to worktree)"

    bundle = bundle_root.as_posix()
    if gate_status.startswith("PASSED"):
        gate_skip = (
            "pre_dispatch_gate already PASSED — skip directly to Step 2. "
            "Do not re-run pre_dispatch_gate.sh or preflight."
        )
    elif gate_status.startswith("FAILED") or gate_status.startswith("UNKNOWN"):
        gate_path = (
            gate_script.resolve().as_posix()
            if gate_script
            else f"{bundle}/scripts/pre_dispatch_gate.sh"
        )
        gate_skip = (
            f"pre_dispatch_gate status: {gate_status}\n\n"
            "**Step 1 — Pre-dispatch gate:** re-run serial gate "
            f"(parallel subagent gate runs in handoff, not in worker session):\n"
            f"```bash\nbash {gate_path} {plan_id}\n```\n"
            "Resolve failures before Step 2."
        )
    else:
        gate_skip = f"pre_dispatch_gate status: {gate_status} — re-run if needed before Step 2."
    gate_script_line = (
        f"gate_script: {gate_script.resolve().as_posix()}" if gate_script else "gate_script: none"
    )
    step1_label = "Step 1 — Pre-dispatch gate (if needed)"
    notify = notification_overlay or {}
    notify_lifecycle = notify.get("notify_lifecycle", "true")
    walk_away_mode = notify.get("walk_away_mode", "false")
    notify_deliver = notify.get("notify_deliver_resolved", "unknown")

    gate_body = _gate_card_body(plan_id)
    gate_body_escaped = gate_body.replace('\\', '\\\\').replace('"', '\\"')

    return f"""Type: {HANDOFF_TYPE}
plan_id: {plan_id}
Plan: {plan_path}
cards_yaml: {cards_yaml_path or "none"}
Repo: {repo_root}
working_branch: {working_branch}
BUNDLE_ROOT: {bundle}
{gate_script_line}
gateway_at_handoff: {gateway_at_handoff}
pre_dispatch_gate: {gate_status}
notify_lifecycle: {notify_lifecycle}
walk_away_mode: {walk_away_mode}
notify_deliver_resolved: {notify_deliver}
cron_provision: {cron_provision}
kanban_board: {kanban_board}
board_cmd: hermes kanban --board {kanban_board}

## FIRST ACTION (execute in order — do not read the Plan file)

1. `skill_view("kanban-advanced:kanban-orchestrator")`
2. **Step 0** — Gateway check (below)
3. **{step1_label}** — only when stamp is not `PASSED`
4. **Step 2** — Create gate card; verify crons (pre-provisioned at handoff)

## Decomposition runbook

You are the **{orchestrator_profile}** profile. This is a board-mediated handoff —
SOP-only, no `agent -p` block, not a coding task.

**Do not read the full Plan file — execute this runbook only.** Use `Plan:` for metadata.
**Post-exec branch on stamped `walk_away_mode`** (`{walk_away_mode}`) — not live overlay.

### Step 0 — Board + Gateway

This handoff runs on board `{kanban_board}`. Export before all commands:
```bash
export KANBAN_BOARD="{kanban_board}"
```

Gateway check:
```bash
hermes gateway status
```

**STOP** if gateway is not running — this card will sit in `ready` with no dispatcher.

### Step 1 — Pre-dispatch gate

{gate_skip}

### Step 2 — Create gate card; verify crons (pre-provisioned)

Crons were provisioned in the **default profile session** before this handoff was created
(`cron_provision: {cron_provision}`). **Do not run `--create` unless `--check` fails.**

```bash
# Idempotency: reuse existing gate for this plan_id (re-spawn guard)
GATE_ID=$(hermes kanban --board "$KANBAN_BOARD" list 2>/dev/null | while IFS= read -r line; do
  tid=$(echo "$line" | awk '{{print $1}}')
  [[ "$tid" == t_* ]] || continue
  hermes kanban --board "$KANBAN_BOARD" show "$tid" 2>/dev/null | grep -qF "plan_id: {plan_id}" && echo "$tid" && break
done)
if [[ -z "$GATE_ID" ]]; then
  hermes kanban --board "$KANBAN_BOARD" create "Gate — {plan_id}" --assignee {orchestrator_profile} --body "{gate_body_escaped}"
  GATE_ID=$(hermes kanban --board "$KANBAN_BOARD" list 2>/dev/null | while IFS= read -r line; do
    tid=$(echo "$line" | awk '{{print $1}}')
    [[ "$tid" == t_* ]] || continue
    hermes kanban --board "$KANBAN_BOARD" show "$tid" 2>/dev/null | grep -qF "plan_id: {plan_id}" && echo "$tid" && break
  done)
fi
echo "Gate: $GATE_ID"
hermes kanban --board "$KANBAN_BOARD" block --kind dependency "$GATE_ID" "Gate — awaiting links"
bash {bundle}/scripts/provision_kanban_crons.sh --check
```

Wave crons (auto-unblock, board-keeper) use `deliver=local` and `no_agent=true` — gateway must run.
When `notify_lifecycle` is `{notify_lifecycle}`, lifecycle cron deliver is `{notify_deliver}` (not local).

**If `--check` fails**, re-create once idempotently then re-check:
```bash
bash {bundle}/scripts/provision_kanban_crons.sh --create --plan-id {plan_id}
bash {bundle}/scripts/provision_kanban_crons.sh --check
```

**STOP if `--check` still fails — do not create implementation cards.**

### Step 3 — Decompose

Substitute `<gate_id>` from Step 2:
```bash
python3 {bundle}/scripts/kanban_decompose.py {decompose_source} --from-handoff --gate-id <gate_id> --no-crons
```
{source_note} — block-on-create; never `--triage`, never `--parent` on create. Crons already provisioned.

### Step 4 — Validate

```bash
bash {bundle}/scripts/validate_board.sh
```
Fix every structural failure before proceeding.

### Step 5 — Complete gate

```bash
hermes kanban --board "$KANBAN_BOARD" complete <gate_id> --summary "Gate complete. Auto-unblock: <cron1_id>. Board-keeper: <cron2_id>. N cards dispatched."
```

Then perform ongoing orchestrator duties (monitor, reconcile, final audit).

---

**Self-referential exception:** if this plan modifies the kanban-advanced governance
infrastructure itself, block this card and notify the operator to run decomposition
manually.

When done, complete this card: `hermes kanban --board "$KANBAN_BOARD" complete <this_card_id> --summary "Decomposed {plan_id}: gate=<gate_id>, N impl cards."`
"""


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a board-mediated orchestrator handoff card."
    )
    parser.add_argument("--plan", required=True, help="Path to the optimized plan file")
    parser.add_argument("--plan-id", default="", help="Override plan_id (else derived)")
    parser.add_argument("--dry-run", action="store_true", help="Print the card, don't create")
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="Skip gateway/dispatcher hard-checks (card will sit until dispatch resumes)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="After operator approval, archive non-running plan cards before handoff",
    )
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Print existing open handoff card ID and exit (no creation)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Auto-clean stale git state (branches, worktrees, attestation) before handoff",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument(
        "--skip-cron-provision",
        action="store_true",
        help="Skip provision_kanban_crons (tests or manual recovery only)",
    )
    args = parser.parse_args()

    def emit(payload: dict) -> None:
        if args.json:
            print(json.dumps(payload))
        else:
            for key, val in payload.items():
                print(f"{key}: {val}")

    plan_path = Path(args.plan).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path).resolve()
    if not plan_path.is_file():
        emit({"ok": False, "error": f"plan file not found: {plan_path}"})
        return 5

    plan_id = _derive_plan_id(plan_path, args.plan_id or None)
    if not plan_id:
        emit({"ok": False, "error": "could not determine plan_id"})
        return 5

    # Export for preflight.sh plan backup check
    os.environ["KANBAN_PLAN_ID"] = plan_id

    project_root = _find_project_root(plan_path.parent)
    overlay = _read_overlay(project_root)
    orchestrator_profile = overlay.get("orchestrator_profile", "kanban-advanced-orchestrator")
    if orchestrator_profile == "orchestrator":
        orchestrator_profile = "kanban-advanced-orchestrator"
    working_branch = overlay.get("working_branch", "main")

    bundle_root = _resolve_bundle_root(project_root, overlay)
    if bundle_root is None:
        bundle_root = project_root / "hermes-kanban-advanced-workflow"

    cards_yaml_path = _discover_cards_yaml(plan_id, plan_path, project_root, overlay)

    # Clean up empty boards from prior failed handoff attempts
    _archive_prior_boards(plan_id)

    # Create per-plan board (idempotent)
    kanban_board = _create_plan_board(plan_id)
    os.environ["HERMES_KANBAN_BOARD"] = kanban_board

    def _fail(rc: int) -> int:
        """Archive the board on failure, then return the exit code."""
        _archive_board(kanban_board)
        return rc

    board_ok, board_msg, archived = _check_board_cleanliness(
        plan_id, force=args.force
    )
    if not board_ok:
        emit({
            "ok": False,
            "error": "board_not_clean",
            "detail": board_msg,
            "plan_id": plan_id,
            "fix": "Confirm with operator, archive listed cards, or re-run with --force",
        })
        return _fail(7)

    # Git freshness check (stale branches, worktrees, attestation from prior runs)
    git_ok, git_msg = _check_git_freshness(plan_id, project_root)
    if args.fresh and not git_ok:
        subprocess.run(
            ["bash", str(bundle_root / "scripts" / "git_safe_cleanup.sh"),
             "--clean", "--plan-id", plan_id],
            cwd=str(project_root)
        )
        git_ok, git_msg = _check_git_freshness(plan_id, project_root)
        if not git_ok:
            emit({
                "ok": False,
                "error": "git_cleanup_failed",
                "detail": git_msg,
                "plan_id": plan_id,
            })
            return _fail(7)
    elif not git_ok:
        emit({
            "ok": False,
            "error": "git_state_not_clean",
            "detail": git_msg,
            "plan_id": plan_id,
            "fix": "Run: bash scripts/git_safe_cleanup.sh --clean --plan-id " + plan_id,
        })
        return _fail(7)

    # Always run serial pre_dispatch_gate at handoff time.
    # Parallel subagent gate (delegate_task) is unreliable on Windows —
    # subagents don't survive kanban worker session boundaries.
    # When Hermes core fixes delegate_task, re-enable the parallel path here.
    gate_status, gate_script = _run_pre_dispatch_gate(plan_id, project_root, overlay)
    gateway_stamp, _gateway_ok = _gateway_status_stamp()

    title = f"Decompose: {plan_id}"

    # ── Preconditions (gateway required for cron provision) ────────────────
    if not _orchestrator_profile_exists(orchestrator_profile):
        emit({
            "ok": False,
            "error": f"orchestrator profile '{orchestrator_profile}' not found",
            "fix": f"hermes kanban-advanced init  (creates {orchestrator_profile} with role-only skills)",
        })
        return _fail(2)

    if not args.allow_offline:
        settings = _kanban_settings()
        if not settings["dispatch_in_gateway"]:
            emit({
                "ok": False,
                "error": "kanban.dispatch_in_gateway is false — the gateway will not claim the handoff card",
                "fix": "hermes config set kanban.dispatch_in_gateway true",
            })
            return _fail(4)
        if settings["auto_decompose"]:
            emit({
                "ok": False,
                "error": "kanban.auto_decompose is true — the handoff card would be LLM-decomposed into stub children",
                "fix": "hermes config set kanban.auto_decompose false",
            })
            return _fail(4)
        if not _gateway_running():
            emit({
                "ok": False,
                "error": "gateway is not running — no dispatcher to claim the handoff card",
                "fix": "hermes gateway run   (or pass --allow-offline to create the card anyway)",
            })
            return _fail(3)

    notification_overlay = _resolve_notification_overlay(project_root, overlay)
    if args.skip_cron_provision:
        cron_stamp = "SKIPPED (manual/test)"
        cron_ok = True
    else:
        cron_stamp, cron_ok, cron_detail = _run_cron_provision(
            plan_id,
            bundle_root,
            project_root,
            dry_run=args.dry_run,
        )
        if not cron_ok and not args.dry_run:
            emit({
                "ok": False,
                "error": "cron_provision_failed",
                "detail": cron_detail,
                "cron_provision": cron_stamp,
                "plan_id": plan_id,
                "fix": (
                    "Run from default profile: "
                    f"bash {bundle_root.as_posix()}/scripts/provision_kanban_crons.sh "
                    f"--create --plan-id {plan_id} && "
                    f"bash {bundle_root.as_posix()}/scripts/provision_kanban_crons.sh --check"
                ),
            })
            return _fail(8)

    body = _build_body(
        plan_id, plan_path, project_root, working_branch,
        orchestrator_profile,
        kanban_board=kanban_board,
        bundle_root=bundle_root,
        cards_yaml_path=cards_yaml_path,
        gate_status=gate_status,
        gate_script=gate_script,
        gateway_at_handoff=gateway_stamp,
        notification_overlay=notification_overlay,
        cron_provision=cron_stamp,
    )

    # ── Idempotency ────────────────────────────────────────────────────────
    existing = _find_open_handoff(plan_id, title)
    if existing:
        if args.reuse:
            print(existing)
            return 0
        emit({"ok": True, "reused": True, "id": existing, "title": title,
              "plan_id": plan_id, "cron_provision": cron_stamp})
        return 0

    if args.dry_run:
        emit({"ok": True, "dry_run": True, "title": title, "assignee": orchestrator_profile,
              "plan_id": plan_id, "cron_provision": cron_stamp})
        print(body)
        return 0

    # ── Create ─────────────────────────────────────────────────────────────
    idem_key = f"kanban-advanced-handoff:{plan_id}"
    create = _hermes(
        "kanban", "create", title,
        "--assignee", orchestrator_profile,
        "--body", body,
        "--idempotency-key", idem_key,
        "--json",
        timeout=30,
    )
    if create.returncode != 0:
        emit({"ok": False, "error": "card creation failed", "stderr": create.stderr.strip()})
        return _fail(6)

    card_id = None
    try:
        card_id = json.loads(create.stdout).get("id")
    except Exception:
        m = re.search(r"t_[a-zA-Z0-9]{8}", create.stdout)
        card_id = m.group(0) if m else None

    if not card_id:
        emit({"ok": False, "error": "could not parse created card id", "raw": create.stdout[:200]})
        return _fail(6)

    emit({"ok": True, "reused": False, "id": card_id, "title": title,
          "assignee": orchestrator_profile, "plan_id": plan_id,
          **({"archived": archived} if archived else {})})
    return 0


if __name__ == "__main__":
    sys.exit(main())
