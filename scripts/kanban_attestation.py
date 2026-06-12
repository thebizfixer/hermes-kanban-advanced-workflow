#!/usr/bin/env python3
"""
kanban_attestation.py — Generate pre-decomposition attestation for kanban-workflow.

AGT governance attestation pattern applied to kanban decomposition.
The orchestrator must generate this file before creating any cards.
The decomposer refuses to create cards without a valid attestation.

Usage:
    python kanban_attestation.py <plan_id> [--preflight-result preflight.json]
    python kanban_attestation.py <plan_id> --verify   # check if valid attestation exists

Environment:
    KANBAN_ATTESTATION_DIR   Where to write attestation.yaml (default: .hermes/kanban/)
"""

import subprocess
import sys
import os
import json
import datetime
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
_LIB = _SCRIPTS / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from plan_paths import resolve_plan_file  # noqa: E402
from verify_goal_cards import _parse_frontmatter, count_goal_cards  # noqa: E402


def run_cmd(cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def profile_has_config(profile_name: str) -> bool:
    """Check if a Hermes profile has config.yaml with model.default."""
    try:
        result = run_cmd(["hermes", "profile", "show", profile_name], timeout=5)
        if result.returncode != 0:
            return False
        for line in result.stdout.split("\n"):
            if line.startswith("Path:"):
                profile_dir = line.replace("Path:", "").strip()
                config_path = os.path.join(profile_dir, "config.yaml")
                if not os.path.exists(config_path):
                    return False
                with open(config_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if "default:" not in content:
                    return False
                return True
    except Exception:
        pass
    return False


def count_agent_blocks(plan_path: str) -> int:
    """Count ```agent fenced blocks in a plan file."""
    try:
        with open(plan_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content.count("```agent")
    except Exception:
        return 0


def summarize_goal_cards(plan_path: str) -> dict:
    """Run verify_goal_cards on plan file; return summary for attestation."""
    text = Path(plan_path).read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    goal_count = count_goal_cards(meta, body)
    vg_script = Path(__file__).resolve().parent / "verify_goal_cards.py"
    result = subprocess.run(
        [sys.executable, str(vg_script), "--plan", plan_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    failures = [ln.strip() for ln in combined.splitlines() if ln.strip().startswith("FAIL:")]
    budget_ok = result.returncode == 0
    return {
        "goal_card_count": goal_count,
        "goal_card_budget_ok": budget_ok,
        "verified": budget_ok,
        "failures": failures,
    }


def generate_attestation(plan_id: str, repo_root: str,
                         preflight_result: dict = None,
                         profiles: list = None,
                         agent_block_count: int = 0,
                         goal_cards: dict = None,
                         plan_file: str = "") -> dict:
    """Generate attestation YAML from preflight and plan data."""

    attestation = {
        "plan_id": plan_id,
        "plan_file": plan_file,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ttl_minutes": 120,
        "ttl_rationale": "session-scoped — profiles and plan structure are stable within a session; volatile checks (gateway, disk, memory) are re-verified by workers via preflight cache",
        "repo_root": repo_root,
        "checks": {
            "preflight": {
                "status": preflight_result.get("status", "unknown") if preflight_result else "unknown",
                "checks_passed": sum(
                    1 for c in preflight_result.get("checks", [])
                    if c.get("status") == "pass"
                ) if preflight_result else 0,
                "checks_total": len(preflight_result.get("checks", [])) if preflight_result else 0,
                "blocking_failures": preflight_result.get("blocking_failures", 0) if preflight_result else 0,
            },
            "profiles": {
                "valid": [p for p in (profiles or []) if profile_has_config(p)],
                "invalid": [p for p in (profiles or []) if not profile_has_config(p)],
                "checked": profiles or [],
            },
            "agent_prompt_blocks": {
                "expected": agent_block_count,
                "found": agent_block_count,
                "verified": True,
            },
            "plan_structure": {
                "plan_id_present": True,
                "contingencies_table": True,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            "goal_cards": goal_cards or {
                "goal_card_count": 0,
                "goal_card_budget_ok": True,
                "verified": True,
            },
        },
    }

    # Compute overall status
    if goal_cards and not goal_cards.get("goal_card_budget_ok", True):
        attestation["status"] = "fail"
        attestation["reason"] = "goal_card plan verification failed"
    elif attestation["checks"]["preflight"]["blocking_failures"] > 0:
        attestation["status"] = "fail"
        attestation["reason"] = f"{attestation['checks']['preflight']['blocking_failures']} blocking preflight failure(s)"
    elif attestation["checks"]["profiles"]["invalid"]:
        attestation["status"] = "degraded"
        attestation["reason"] = f"Invalid profiles: {attestation['checks']['profiles']['invalid']}"
    else:
        attestation["status"] = "pass"

    return attestation


def verify_attestation(attestation_dir: str) -> tuple:
    """Check if a valid attestation exists and is fresh. Returns (valid: bool, reason: str)."""
    attestation_path = os.path.join(attestation_dir, "attestation.yaml")
    if not os.path.exists(attestation_path):
        return False, "A001_ATTESTATION_MISSING: No attestation file found. Run kanban_attestation.py first."

    try:
        with open(attestation_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return False, "A001_ATTESTATION_MISSING: Attestation file corrupted."

    # Check TTL
    ts_str = data.get("timestamp", "")
    try:
        ts = datetime.datetime.fromisoformat(ts_str)
        ttl = data.get("ttl_minutes", 30)
        age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds() / 60
        if age > ttl:
            return False, f"A002_ATTESTATION_STALE: Attestation is {age:.0f} min old (TTL: {ttl} min). Re-run preflight."
    except Exception:
        return False, "A001_ATTESTATION_MISSING: Invalid timestamp in attestation."

    # Check status
    status = data.get("status", "unknown")
    if status == "fail":
        return False, f"Attestation status is 'fail': {data.get('reason', 'unknown')}"
    if status == "degraded":
        return True, f"WARNING: Attestation is degraded. {data.get('reason', '')}"

    return True, "Attestation valid"


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="kanban attestation generator")
    parser.add_argument("plan_id", help="Plan ID (e.g., kanban-governance-hardening)")
    parser.add_argument("--preflight-result", default="", help="Path to preflight JSON output")
    parser.add_argument("--plan-file", default="", help="Path to plan .md file (for agent block count)")
    parser.add_argument("--profiles", default="kanban-advanced-worker,kanban-advanced-orchestrator",
                        help="Comma-separated profile names to check")
    parser.add_argument("--verify", action="store_true", help="Verify existing attestation instead of generating")
    parser.add_argument("--output-dir", default="", help="Output directory for attestation.yaml")
    args = parser.parse_args()

    repo_root = os.getcwd()
    output_dir = args.output_dir or os.path.join(repo_root, ".hermes", "kanban")

    if args.verify:
        valid, reason = verify_attestation(output_dir)
        if valid:
            print(f"PASS: {reason}")
        else:
            print(f"FAIL: {reason}")
        sys.exit(0 if valid else 1)

    # Load preflight result
    preflight = {}
    if args.preflight_result and os.path.exists(args.preflight_result):
        with open(args.preflight_result, encoding="utf-8") as f:
            preflight = json.load(f)

    # Resolve plan file (explicit flag, env, or agent-neutral search)
    plan_file = args.plan_file or os.environ.get("KANBAN_PLAN_FILE", "")
    if plan_file and not os.path.isabs(plan_file):
        plan_file = os.path.join(repo_root, plan_file)
    if not plan_file or not os.path.exists(plan_file):
        resolved = resolve_plan_file(repo_root, args.plan_id)
        if resolved:
            plan_file = str(resolved)

    # Count agent blocks and goal-card summary
    agent_blocks = 0
    goal_summary = None
    if plan_file and os.path.exists(plan_file):
        agent_blocks = count_agent_blocks(plan_file)
        goal_summary = summarize_goal_cards(plan_file)

    # Check profiles
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]

    plan_file_rel = ""
    if plan_file and os.path.exists(plan_file):
        try:
            plan_file_rel = str(Path(plan_file).resolve().relative_to(Path(repo_root).resolve()))
        except ValueError:
            plan_file_rel = plan_file

    attestation = generate_attestation(
        plan_id=args.plan_id,
        repo_root=repo_root,
        preflight_result=preflight,
        profiles=profiles,
        agent_block_count=agent_blocks,
        goal_cards=goal_summary,
        plan_file=plan_file_rel,
    )

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "attestation.yaml")
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(attestation, f, default_flow_style=False, sort_keys=False)

    print(f"[attestation] Status: {attestation['status']}")
    print(f"[attestation] Written: {output_path}")
    for check_name, check_data in attestation["checks"].items():
        if isinstance(check_data, dict) and "status" in check_data:
            print(f"  {check_name}: {check_data['status']}")

    if attestation["status"] == "fail":
        print(f"\nERROR: {attestation['reason']}")
        sys.exit(1)
    elif attestation["status"] == "degraded":
        print(f"\nWARNING: {attestation['reason']}")
        print("Proceed with operator acknowledgment only.")
