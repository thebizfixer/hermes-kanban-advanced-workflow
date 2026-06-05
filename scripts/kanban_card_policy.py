#!/usr/bin/env python3
"""
kanban_card_policy.py — Validate kanban card bodies against policy rules before dispatch.

AGT PolicyEvaluator pattern applied to kanban card body validation.
Called by orchestrator after all cards are created and linked, before unblocking the gate.

Usage:
    python kanban_card_policy.py <task_id> [--profile balanced]
    python kanban_card_policy.py --all [--profile strict]

Environment:
    KANBAN_POLICY_PROFILE   Enforcement level: advisory | balanced | strict (default: balanced)
    KANBAN_POLICY_PATH      Path to card-body-policy.yaml
"""

import subprocess
import sys
import os
import yaml
from typing import List, Tuple, Optional


# ── Policy loader ──────────────────────────────────────────────────────

def load_policy(policy_path: str) -> dict:
    """Load card body policy from YAML. Falls back to built-in minimal policy."""
    try:
        with open(policy_path) as f:
            return yaml.safe_load(f)
    except Exception:
        pass
    # Built-in fallback
    return {
        "default_action": "deny",
        "rules": [
            {"name": "require-files-line", "condition": "body does not contain 'Files:'",
             "action": "deny", "reason": "Card body must contain a Files: line", "error_code": "P001"},
            {"name": "require-agent-block", "condition": "body does not contain '```agent'",
             "action": "deny", "reason": "Card body must contain an agent -p block", "error_code": "P002"},
        ],
    }


# ── Card body retrieval ────────────────────────────────────────────────

def get_card_body(task_id: str) -> str:
    """Retrieve card body via hermes kanban show."""
    result = subprocess.run(
        ["hermes", "kanban", "show", task_id],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        print(f"ERROR: Cannot retrieve card body for {task_id}: {result.stderr}")
        return ""
    return result.stdout


def get_all_card_ids() -> List[str]:
    """Get all task IDs from the board."""
    result = subprocess.run(
        ["hermes", "kanban", "list"],
        capture_output=True, text=True, timeout=10
    )
    ids = []
    for line in result.stdout.split("\n"):
        parts = line.split()
        if parts and parts[0].startswith("t_"):
            ids.append(parts[0])
    return ids


# ── Validation ─────────────────────────────────────────────────────────

def validate_card(task_id: str, body: str, policy: dict) -> List[dict]:
    """Run all policy rules against a card body. Returns list of violations."""
    violations = []
    for rule in policy.get("rules", []):
        condition = rule.get("condition", "")
        if condition == "body does not contain 'Files:'" and "Files:" not in body:
            violations.append(rule)
        elif condition == "body does not contain '```agent'" and "```agent" not in body:
            violations.append(rule)
        elif condition == "body does not contain 'Mode:'" and "Mode:" not in body:
            violations.append(rule)
        elif condition == "Files: count > 3":
            # Count files listed on Files: line
            for line in body.split("\n"):
                if line.startswith("Files:"):
                    count = len([f for f in line.replace("Files:", "").split(",") if f.strip()])
                    if count > 3:
                        violations.append(rule)
                    break
        elif condition == "card was created with --parents flag (known-broken in vanilla hermes)":
            # P008: Body mentions "Depends on" but doesn't reference correct `kanban link` pattern.
            # False-positive avoidance: only flag when body talks about dependencies
            # without mentioning the approved `kanban link` method.
            if ("depends on" in body.lower() or "depends upon" in body.lower()):
                if "kanban link" not in body.lower() and "hermes kanban link" not in body.lower():
                    # Check if parents are listed in the body metadata
                    has_parents = "parents:" in body.lower() and any(
                        pid.strip().startswith("t_") 
                        for pid in body.lower().split("parents:")[-1].split("\n")[0].split(",")
                    )
                    if not has_parents:
                        violations.append(dict(rule, 
                            reason=rule.get("reason", "") + 
                            " Body mentions dependencies without kanban link references or parent metadata."))
        elif (
            condition
            == "HERMES_KANBAN_GOAL_MODE is set and body does not contain 'Acceptance:'"
        ):
            if os.environ.get("HERMES_KANBAN_GOAL_MODE") in ("1", "true", "yes") and "Acceptance:" not in body:
                violations.append(rule)
        elif condition == "card body indicates happy-path turns > 35 ceiling":
            # P009: Count def/class mentions in body as a heuristic for iteration budget.
            # >10 function/class mentions is a signal the card may exceed 35-turn budget.
            import re
            fn_matches = re.findall(r'\b(?:def|class|async\s+def|function)\s+(\w+)', body)
            fn_count = len(fn_matches)
            if fn_count > 10:
                violations.append(dict(rule,
                    reason=f"Card body mentions ~{fn_count} function/class definitions (>10 ceiling). "
                           f"May exceed 35-turn iteration budget. Split into smaller cards."))
    return violations


def apply_policy(task_id: str, violations: List[dict], profile: str) -> Tuple[bool, Optional[str]]:
    """Apply policy profile to violations. Returns (allowed: bool, reason: str)."""
    if not violations:
        return True, None

    violation_codes = [v.get("error_code", "?") for v in violations]
    reasons = "; ".join(v.get("reason", "unknown") for v in violations)

    if profile == "advisory":
        print(f"ADVISORY: {task_id} — {len(violations)} policy violation(s): {', '.join(violation_codes)}")
        print(f"  {reasons}")
        return True, None

    elif profile == "balanced":
        print(f"BLOCK: {task_id} — {len(violations)} policy violation(s): {', '.join(violation_codes)}")
        print(f"  {reasons}")
        subprocess.run(["hermes", "kanban", "block", task_id, reasons])
        return False, reasons

    elif profile == "strict":
        print(f"BLOCK+NOTIFY: {task_id} — {len(violations)} policy violation(s): {', '.join(violation_codes)}")
        print(f"  {reasons}")
        subprocess.run(["hermes", "kanban", "block", task_id, reasons])
        # kanban-notify integration point: trigger gateway notification
        # (handled by kanban-notify skill when it sees the block event)
        return False, reasons

    return True, None


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="kanban card body policy validator")
    parser.add_argument("task_id", nargs="?", default="", help="Task ID to validate")
    parser.add_argument("--all", action="store_true", help="Validate all cards on board")
    parser.add_argument("--profile", default="", help="Policy profile: advisory | balanced | strict")
    parser.add_argument("--policy-path", default="", help="Path to card-body-policy.yaml")
    args = parser.parse_args()

    profile = args.profile or os.environ.get("KANBAN_POLICY_PROFILE", "balanced")
    policy_path = args.policy_path or os.path.join(
        os.getcwd(), "kanban-workflow", "policies", "card-body-policy.yaml"
    )
    policy = load_policy(policy_path)

    task_ids = []
    if args.all:
        task_ids = get_all_card_ids()
    elif args.task_id:
        task_ids = [args.task_id]
    else:
        print("ERROR: Pass a task_id or --all.")
        sys.exit(1)

    if not task_ids:
        print("No cards found on board.")
        sys.exit(0)

    total_violations = 0
    blocked = 0

    for tid in task_ids:
        body = get_card_body(tid)
        if not body:
            print(f"SKIP: {tid} — cannot retrieve body")
            continue

        violations = validate_card(tid, body, policy)
        allowed, reason = apply_policy(tid, violations, profile)

        if not allowed:
            total_violations += len(violations)
            blocked += 1
        else:
            print(f"OK: {tid}" + (f" ({len(violations)} advisory warning(s))" if violations else ""))

    print(f"\n[policy] Profile: {profile}")
    print(f"[policy] Cards checked: {len(task_ids)}")
    print(f"[policy] Cards blocked: {blocked}")
    print(f"[policy] Total violations: {total_violations}")

    sys.exit(0 if blocked == 0 else 1)
