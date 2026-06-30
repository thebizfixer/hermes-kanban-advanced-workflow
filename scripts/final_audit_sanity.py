#!/usr/bin/env python3
"""
final_audit_sanity.py — Two-tier final audit + post-flight remediation loop.

Usage:
    python3 final_audit_sanity.py --plan-id <id> [--tier 1|2|all] [--baseline <ref>]
    python3 final_audit_sanity.py --plan-id <id> --spawn-remediation [--round N]

Exit codes: 0=clean, 1=violations, 2=script error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB = _SCRIPT_DIR / "lib"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from final_audit import (  # noqa: E402
    AuditContext,
    build_remediation_body,
    current_audit_round,
    extract_field,
    filter_violations_by_fingerprints,
    format_violation_summary,
    git_changed_paths,
    group_remediation_cards,
    load_violations_from_reports,
    process_gave_up_remediation_children,
    read_overlay_audit_settings,
    resolve_baseline_sha,
    resolve_working_branch,
    run_escalation_tracker,
    run_tier1,
    run_tier2,
    write_tier_report,
)
from plan_paths import resolve_plan_file  # noqa: E402


def _project_root() -> Path:
    for env in ("KANBAN_PROJECT_ROOT", "HERMES_PROJECT_ROOT"):
        raw = os.environ.get(env, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def _hermes_home() -> Path:
    for env in ("HERMES_HOME", "HERMES_STATE_DIR"):
        raw = os.environ.get(env, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return Path.home() / ".hermes"


def _resolve_kanban_db(plan_id: str = "") -> Path:
    board = os.environ.get("HERMES_KANBAN_BOARD", "").strip()
    if not board and plan_id:
        # Auto-resolve board via resolver singleton
        try:
            from lib.board_resolver import resolve_board_for_plan  # noqa: E402
            resolved = resolve_board_for_plan(plan_id)
            if resolved:
                board = resolved
        except ImportError:
            pass
    if board and board != "default":
        return _hermes_home() / "kanban" / "boards" / board / "kanban.db"
    return _hermes_home() / "kanban.db"


def _counter_path(plan_id: str) -> Path:
    return _hermes_home() / "kanban" / f"remediation_rounds_{plan_id}.json"


def _read_counter(plan_id: str) -> int:
    path = _counter_path(plan_id)
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("rounds", 0))
    except Exception:
        return 0


def _write_counter(plan_id: str, rounds: int) -> None:
    path = _counter_path(plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rounds": rounds, "plan_id": plan_id}), encoding="utf-8")


def _delete_counter(plan_id: str) -> None:
    path = _counter_path(plan_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _load_cards_from_db(plan_id: str, db_path: Path) -> list[dict[str, Any]]:
    import sqlite3

    if not db_path.is_file():
        raise RuntimeError(f"kanban DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    ]
    task_table = "tasks" if "tasks" in tables else None
    if not task_table:
        conn.close()
        raise RuntimeError("tasks table missing in kanban DB")
    rows = conn.execute(
        f"SELECT id, body, status FROM {task_table} WHERE body LIKE ?",
        (f"%plan_id: {plan_id}%",),
    ).fetchall()
    conn.close()
    cards: list[dict[str, Any]] = []
    for row in rows:
        body = row["body"] if row["body"] else ""
        if plan_id not in body:
            continue
        cards.append(
            {
                "task_id": row["id"],
                "body": body,
                "status": row["status"] or "",
            }
        )
    return cards


def _find_audit_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    for card in cards:
        if re.search(r"Type:\s*audit", card.get("body", ""), re.I):
            return card
    for card in cards:
        if "final audit" in card.get("body", "").lower():
            return card
    return None


def _hermes_run(*args: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["hermes", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return result.stdout, result.stderr, result.returncode


def _extract_task_id(output: str) -> str | None:
    for line in output.splitlines():
        if line.strip().startswith("t_"):
            return line.strip().split()[0]
    m = re.search(r"\b(t_[a-zA-Z0-9_-]+)\b", output)
    return m.group(1) if m else None


def _spawn_card(title: str, body: str, assignee: str, parent_id: str) -> str | None:
    out, err, rc = _hermes_run("kanban", "create", title, "--assignee", assignee, "--body", body)
    if rc != 0:
        print(f"WARN: create failed: {err[:300]}", file=sys.stderr)
        return None
    tid = _extract_task_id(out)
    if tid and parent_id:
        _hermes_run("kanban", "link", parent_id, tid)
        _hermes_run("kanban", "block", "--kind", "dependency", tid, "Awaiting remediation wave (auto_unblock when audit re-runs)")
    return tid


def _update_audit_round(audit_id: str, round_num: int) -> None:
    out, _, rc = _hermes_run("kanban", "show", audit_id)
    if rc != 0:
        return
    body = out
    if re.search(r"(?m)^Audit-round:", body):
        body = re.sub(r"(?m)^Audit-round:.*$", f"Audit-round: {round_num}", body)
    else:
        body = f"Audit-round: {round_num}\n{body}"
    _hermes_run("kanban", "edit", audit_id, "--body", body)


def _list_remediation_children(audit_id: str) -> list[dict[str, str]]:
    out, _, rc = _hermes_run("kanban", "list", "--parent", audit_id)
    candidate_ids: list[str] = []
    if rc == 0 and out.strip():
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("t_"):
                candidate_ids.append(parts[0])
    parent_list_ok = bool(candidate_ids)
    if not candidate_ids:
        out, _, rc = _hermes_run("kanban", "list")
        if rc != 0:
            return []
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("t_"):
                candidate_ids.append(parts[0])

    children: list[dict[str, str]] = []
    for tid in candidate_ids:
        detail, _, show_rc = _hermes_run("kanban", "show", tid)
        if show_rc != 0:
            continue
        if "Type: remediation" not in detail and "type: remediation" not in detail.lower():
            continue
        if not parent_list_ok and audit_id not in detail:
            continue
        status = ""
        for ln in detail.splitlines():
            if ln.strip().startswith("status:"):
                status = ln.split(":", 1)[1].strip()
                break
        children.append({"task_id": tid, "body": detail, "status": status})
    return children


def _gave_up_remediation_children(audit_id: str) -> list[dict[str, str]]:
    gave_up: list[dict[str, str]] = []
    for child in _list_remediation_children(audit_id):
        status = child.get("status", "")
        body = child.get("body", "")
        if status == "gave_up" or "gave_up" in body.lower():
            gave_up.append(child)
    return gave_up


def _block_audit_card(audit_id: str, summary: str, dry_run: bool) -> None:
    reason = f"Max final audit remediation rounds exceeded:\n{summary}"
    if dry_run:
        print(f"[DRY-RUN] Would block audit card {audit_id}", file=sys.stderr)
        return
    _hermes_run("kanban", "block", "--kind", "dependency", audit_id, reason)


def _escalate_max_rounds(
    audit_card: dict[str, Any] | None,
    plan_id: str,
    max_rounds: int,
    violations: list[Any],
    repo_root: Path,
    dry_run: bool,
) -> None:
    if not audit_card:
        return
    summary = format_violation_summary(violations)
    reason = (
        f"[escalation:orchestrator:attempt:{max_rounds}] final audit max remediation rounds "
        f"({max_rounds}) exceeded plan_id={plan_id}"
    )
    if dry_run:
        print(f"[DRY-RUN] Would escalate audit {audit_card['task_id']}: {reason}", file=sys.stderr)
        return
    run_escalation_tracker(_SCRIPT_DIR, audit_card["task_id"], reason, repo_root)
    _block_audit_card(audit_card["task_id"], summary, dry_run=False)


def _process_gave_up_before_rerun(
    audit_card: dict[str, Any] | None,
    plan_id: str,
    report_dir: Path,
    repo_root: Path,
    dry_run: bool,
) -> set[tuple[str, str, str, str]]:
    if not audit_card:
        return set()
    gave_up = _gave_up_remediation_children(audit_card["task_id"])
    if not gave_up:
        return set()
    fps = process_gave_up_remediation_children(
        audit_id=audit_card["task_id"],
        plan_id=plan_id,
        report_dir=report_dir,
        repo_root=repo_root,
        scripts_dir=_SCRIPT_DIR,
        gave_up_children=gave_up,
        dry_run=dry_run,
    )
    for child in gave_up:
        print(f"NOTE: escalated gave_up remediation {child['task_id']}", file=sys.stderr)
    return fps


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Final audit two-tier sanity check")
    p.add_argument("--plan-id", required=True)
    p.add_argument("--repo-root", default=str(_project_root()))
    p.add_argument("--baseline", default=None, help="Override baseline ref (default: Audit-baseline-sha from audit card)")
    p.add_argument("--tier", choices=("1", "2", "all"), default="all")
    p.add_argument("--spawn-remediation", action="store_true")
    p.add_argument("--max-rounds", type=int, default=None, help="Override max remediation rounds (default 2)")
    p.add_argument("--round", type=int, default=None)
    p.add_argument("--no-json", action="store_true", help="Suppress tier JSON report writes")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan_id = args.plan_id.strip()
    repo_root = Path(args.repo_root).resolve()
    overrides, max_rounds = read_overlay_audit_settings(repo_root)
    if args.max_rounds is not None:
        max_rounds = args.max_rounds

    plan_path = resolve_plan_file(repo_root, plan_id)
    if not plan_path or not plan_path.is_file():
        print(f"ERROR: plan file not found for plan_id={plan_id}", file=sys.stderr)
        return 2

    db_path = _resolve_kanban_db(plan_id)
    try:
        cards = _load_cards_from_db(plan_id, db_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    audit_card = _find_audit_card(cards)
    audit_body = audit_card.get("body", "") if audit_card else ""
    baseline = args.baseline or resolve_baseline_sha(
        audit_body, repo_root, resolve_working_branch(repo_root)
    )

    # Fallback: if baseline SHA is not in repo (stale attestation from rebased branch),
    # try the Audit-baseline-sha stamped directly on the audit card body.
    if baseline:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{baseline}^{{commit}}"],
            capture_output=True, text=True, cwd=str(repo_root)
        )
        if result.returncode != 0:
            stamped = extract_field(audit_body, "Audit-baseline-sha")
            if stamped and stamped != baseline:
                print(f"WARNING: baseline {baseline[:12]} not in repo, "
                      f"using audit card stamp {stamped[:12]}")
                baseline = stamped

    plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
    ctx = AuditContext(
        plan_id=plan_id,
        repo_root=repo_root,
        baseline=baseline,
        plan_path=plan_path,
        plan_text=plan_text,
        cards=cards,
        overrides=overrides,
        max_remediation_rounds=max_rounds,
    )

    report_dir = repo_root / ".hermes" / "kanban" / "reports"

    try:
        from orchestrator_token_checkpoint import maybe_log_orchestrator_checkpoint  # noqa: E402

        maybe_log_orchestrator_checkpoint(plan_id, "audit-start", note="final_audit_sanity")
    except Exception:
        pass

    if args.spawn_remediation:
        current_rounds = _read_counter(plan_id)
        if current_rounds >= max_rounds:
            print(f"ERROR: max remediation rounds ({max_rounds}) reached", file=sys.stderr)
            return 2

        round_num = args.round
        if round_num is None:
            stamped = extract_field(audit_body, "Audit-round")
            round_num = int(stamped) + 1 if stamped.isdigit() else 1

        gave_up_fps = _process_gave_up_before_rerun(
            audit_card, plan_id, report_dir, repo_root, args.dry_run
        )
        violations = load_violations_from_reports(report_dir, plan_id)
        violations = filter_violations_by_fingerprints(violations, gave_up_fps)
        violations = [v for v in violations if v.severity == "fail"]

        groups = group_remediation_cards(violations)
        overlay = repo_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
        assignee = "kanban-advanced-worker"
        if overlay.is_file():
            for line in overlay.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("worker_profile:"):
                    assignee = line.split(":", 1)[1].strip().strip('"').strip("'") or assignee

        parent_id = audit_card["task_id"] if audit_card else ""
        for i, group in enumerate(groups, start=1):
            body = build_remediation_body(plan_id, group)
            title = f"Final audit remediation {round_num}.{i} — {plan_id}"
            if args.dry_run:
                print(f"[DRY-RUN] Would spawn: {title}")
                continue
            tid = _spawn_card(title, body, assignee, parent_id)
            if tid:
                print(f"Spawned remediation card {tid}")

        _write_counter(plan_id, current_rounds + 1)

        if audit_card and not args.dry_run:
            _update_audit_round(audit_card["task_id"], round_num)
        ret = 1 if violations else 0
        if ret == 0:
            _delete_counter(plan_id)
        return ret

    if audit_card and current_audit_round(audit_body) >= 1:
        _process_gave_up_before_rerun(audit_card, plan_id, report_dir, repo_root, args.dry_run)

    # Run audit tiers
    try:
        tier1_violations = run_tier1(ctx) if args.tier in ("1", "all") else []
        changed = git_changed_paths(baseline, repo_root)
        tier2_violations = run_tier2(ctx, changed) if args.tier in ("2", "all") else []
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    all_fails = [v for v in tier1_violations + tier2_violations if v.severity == "fail"]

    if not args.no_json:
        round_extra: dict[str, Any] = {}
        if audit_card:
            round_extra["audit_round"] = current_audit_round(audit_body)
        tier1_extra = {"baseline": baseline, **round_extra}
        write_tier_report(report_dir, plan_id, "tier1", tier1_violations, tier1_extra)
        write_tier_report(report_dir, plan_id, "tier2", tier2_violations, round_extra or None)

    if all_fails:
        for v in all_fails:
            print(f"[{v.tier}] {v.class_name}: {v.path} — {v.detail}", file=sys.stderr)
        if audit_card and current_audit_round(audit_body) >= max_rounds:
            _escalate_max_rounds(audit_card, plan_id, max_rounds, all_fails, repo_root, args.dry_run)
        return 1
    print(f"Final audit clean for plan_id={plan_id}")
    _delete_counter(plan_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
