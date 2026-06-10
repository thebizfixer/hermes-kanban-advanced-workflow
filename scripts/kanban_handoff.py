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
"""

from __future__ import annotations

import argparse
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


# ── hermes CLI helpers ───────────────────────────────────────────────────────

def _hermes(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    # Force UTF-8 decoding: hermes prints non-ASCII (table glyphs, em dashes) that
    # crash the default cp1252 reader on Windows.
    return subprocess.run(
        ["hermes", *args],
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


def _build_body(plan_id: str, plan_path: Path, repo_root: Path, working_branch: str,
                orchestrator_profile: str,
                cards_yaml_path: Path | None = None) -> str:
    """SOP-only handoff body. NO ``agent -p`` block by design."""
    if cards_yaml_path and cards_yaml_path.is_file():
        decompose_cmd = (
            f'python3 scripts/kanban_decompose.py --cards-yaml "{cards_yaml_path}" '
            f'--gate-id <gate_id>'
        )
        decompose_note = (
            f"Cards YAML exists at {cards_yaml_path} — it has richer per-card "
            f"workspace/branch metadata. Pass --gate-id after you create the gate "
            f"in Step 3 so the decomposer reuses it instead of creating a duplicate."
        )
    else:
        decompose_cmd = (
            f'python3 scripts/kanban_decompose.py --plan "{plan_path}" '
            f'--gate-id <gate_id>'
        )
        decompose_note = (
            "Pass --gate-id after you create the gate in Step 3 so the decomposer "
            "reuses it instead of auto-creating a duplicate gate card."
        )

    return f"""Type: {HANDOFF_TYPE}
plan_id: {plan_id}
Plan: {plan_path}
Repo: {repo_root}
working_branch: {working_branch}

You are running under the **{orchestrator_profile}** profile via a board-mediated
handoff. Execute the kanban-advanced decomposition SOP for the plan above. This is
NOT a coding task — there is intentionally no `agent -p` block. Run the SOP from
your terminal:

1. Load the skill: skill_view("kanban-advanced:kanban-orchestrator").
2. PREFLIGHT — `hermes kanban-advanced preflight {plan_id}` (or
   `bash scripts/preflight.sh`). Resolve any gate failure before continuing.
3. ATTESTATION + GATE — complete Step 0c/0d attestation; create gate card:
   `hermes kanban create gate --assignee {orchestrator_profile}`
   `hermes kanban block <gate_id> "Gate — awaiting links"`
   Then immediately create crons (auto-unblock 1m + board-keeper 3m) and verify
   both are running BEFORE creating any implementation cards.
4. DECOMPOSE — {decompose_cmd}
   {decompose_note}
   (block-on-create; never `--triage`, never `--parent` on create).
5. VALIDATE — `bash scripts/validate_board.sh`. Fix every structural failure.
6. COMPLETE GATE — only after validate passes, complete the gate card to release
   wave 1. Then perform ongoing orchestrator duties (monitor, reconcile, audit).

Self-referential exception: if this plan modifies the kanban-advanced governance
infrastructure itself, do NOT auto-run decomposition — block this card and notify
the operator to run it manually.

When decomposition is complete and the board is validated, complete this card with
a summary listing the gate id and the number of cards dispatched.
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
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
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

    # Prefer --cards-yaml when it exists alongside the plan (richer per-card metadata).
    cards_yaml_path: Path | None = None
    for candidate in [
        plan_path.parent / f"{plan_id}.yaml",
        plan_path.with_suffix(".yaml"),
    ]:
        if candidate.is_file():
            cards_yaml_path = candidate
            break

    project_root = _find_project_root(plan_path.parent)
    overlay = _read_overlay(project_root)
    orchestrator_profile = overlay.get("orchestrator_profile", "orchestrator")
    working_branch = overlay.get("working_branch", "main")

    title = f"Decompose: {plan_id}"
    body = _build_body(
        plan_id, plan_path, project_root, working_branch,
        orchestrator_profile, cards_yaml_path=cards_yaml_path,
    )

    # ── Preconditions ──────────────────────────────────────────────────────
    if not _orchestrator_profile_exists(orchestrator_profile):
        emit({
            "ok": False,
            "error": f"orchestrator profile '{orchestrator_profile}' not found",
            "fix": f"hermes profile create {orchestrator_profile} --clone  (or: hermes kanban-advanced init)",
        })
        return 2

    if not args.allow_offline:
        settings = _kanban_settings()
        if not settings["dispatch_in_gateway"]:
            emit({
                "ok": False,
                "error": "kanban.dispatch_in_gateway is false — the gateway will not claim the handoff card",
                "fix": "hermes config set kanban.dispatch_in_gateway true",
            })
            return 4
        if settings["auto_decompose"]:
            emit({
                "ok": False,
                "error": "kanban.auto_decompose is true — the handoff card would be LLM-decomposed into stub children",
                "fix": "hermes config set kanban.auto_decompose false",
            })
            return 4
        if not _gateway_running():
            emit({
                "ok": False,
                "error": "gateway is not running — no dispatcher to claim the handoff card",
                "fix": "hermes gateway run   (or pass --allow-offline to create the card anyway)",
            })
            return 3

    # ── Idempotency ────────────────────────────────────────────────────────
    existing = _find_open_handoff(plan_id, title)
    if existing:
        emit({"ok": True, "reused": True, "id": existing, "title": title,
              "plan_id": plan_id})
        return 0

    if args.dry_run:
        emit({"ok": True, "dry_run": True, "title": title, "assignee": orchestrator_profile,
              "plan_id": plan_id})
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
        return 6

    card_id = None
    try:
        card_id = json.loads(create.stdout).get("id")
    except Exception:
        m = re.search(r"t_[a-zA-Z0-9]{8}", create.stdout)
        card_id = m.group(0) if m else None

    if not card_id:
        emit({"ok": False, "error": "could not parse created card id", "raw": create.stdout[:200]})
        return 6

    emit({"ok": True, "reused": False, "id": card_id, "title": title,
          "assignee": orchestrator_profile, "plan_id": plan_id})
    return 0


if __name__ == "__main__":
    sys.exit(main())
