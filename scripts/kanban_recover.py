#!/usr/bin/env python3
"""
kanban_recover.py — Sad-path recovery script implementing detection→isolation→recovery→verification.

AEP error registry + AGT recovery pattern applied to kanban failure modes.
Maps every error code from error-codes.yaml to a deterministic recovery action.

Usage:
    python kanban_recover.py <task_id> <error_code>
    python kanban_recover.py --cascade         # triage multi-failure cascade
    python kanban_recover.py --list             # list all known recovery actions

Environment:
    KANBAN_REGISTRY_PATH   Path to error-codes.yaml
    KANBAN_RECOVERY_DIR    Where recovery state is tracked
"""

import subprocess
import sys
import os
import json
import datetime
import shutil
from pathlib import Path
from typing import Optional

import yaml


# ── Registry loader ────────────────────────────────────────────────────

def load_registry(registry_path: str) -> dict:
    try:
        with open(registry_path) as f:
            data = yaml.safe_load(f)
            return {c["code"]: c for c in (data.get("codes") or {}).values()}
    except Exception:
        pass
    return {}


# ── Recovery state ─────────────────────────────────────────────────────

def recovery_state_path(recovery_dir: str) -> str:
    return os.path.join(recovery_dir, "recovery-state.json")


def load_recovery_state(recovery_dir: str) -> dict:
    try:
        with open(recovery_state_path(recovery_dir)) as f:
            return json.load(f)
    except Exception:
        return {"actions": [], "cascade_events": []}


def save_recovery_state(recovery_dir: str, state: dict):
    os.makedirs(recovery_dir, exist_ok=True)
    with open(recovery_state_path(recovery_dir), "w") as f:
        json.dump(state, f, indent=2, default=str)


def log_recovery(recovery_dir: str, task_id: str, error_code: str, action: str, result: str):
    state = load_recovery_state(recovery_dir)
    state["actions"].append({
        "task_id": task_id,
        "error_code": error_code,
        "action": action,
        "result": result,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    save_recovery_state(recovery_dir, state)


# ── Recovery actions ───────────────────────────────────────────────────

def recover_e001_file_not_in_diff(task_id: str, workspace: str, registry: dict):
    """E001: Agent missed a file. Check agent output, retry with explicit path."""
    print(f"[recover] E001: File not in diff for {task_id}")
    print("[recover] Action: Block task for manual review. Agent missed a required file.")
    subprocess.run(["hermes", "kanban", "block", task_id,
                    "E001: Agent missed a file. Check Files: line and agent output."])


def recover_e002_unlisted_change(task_id: str, workspace: str, registry: dict):
    """E002: Auto-reverted by evaluation chain. Just log."""
    print(f"[recover] E002: Unlisted changes auto-reverted for {task_id}")
    print("[recover] Action: None needed. Evaluation chain Step 2 already reverted unlisted files.")


def recover_e003_test_failure(task_id: str, workspace: str, registry: dict):
    """E003: Tests failed. Block for fix."""
    print(f"[recover] E003: Test failure for {task_id}")
    print("[recover] Action: Block task. Review diff, fix code, re-run agent.")
    subprocess.run(["hermes", "kanban", "block", task_id, "E003: Tests failed. Review and fix."])


def recover_e004_commit_mismatch(task_id: str, workspace: str, registry: dict):
    """E004: Commit message mismatch. Try amending."""
    print(f"[recover] E004: Commit mismatch for {task_id}")
    subprocess.run(["hermes", "kanban", "block", task_id,
                    "E004: Commit message doesn't match card body. Amend or update card."])


def recover_e006_zero_output(task_id: str, workspace: str, registry: dict):
    """E006: Agent produced no changes."""
    print(f"[recover] E006: Zero output for {task_id}")
    print("[recover] Action: Check workspace type (must be worktree), agent auth, prompt clarity.")
    subprocess.run(["hermes", "kanban", "block", task_id,
                    "E006: Zero output — agent produced no changes. Check workspace/auth/prompt."])


def recover_e007_disk_full(task_id: str, workspace: str, registry: dict):
    """E007: Disk full. Block all cards."""
    print("[recover] E007: DISK FULL — blocking all cards on board.")
    result = subprocess.run(["hermes", "kanban", "list"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        parts = line.split()
        if parts and parts[0].startswith("t_"):
            tid = parts[0]
            subprocess.run(["hermes", "kanban", "block", tid, "E007: Disk full — blocked by recovery script"])
    # Free space: suggest common culprits
    print("[recover] Check: docker system prune, pip cache purge, git gc, /tmp cleanup")


def recover_e009_push_to_development(task_id: str, workspace: str, registry: dict):
    """E009: Agent pushed to development."""
    print(f"[recover] E009: Unauthorized push to development for {task_id}")
    repo_root = workspace
    subprocess.run(["git", "push", "origin", "--delete", "development"], cwd=repo_root)
    subprocess.run(["hermes", "kanban", "block", task_id,
                    "E009: Agent pushed to development. Remote branch deleted. Agent restart required."])


def recover_e011_cross_mount(task_id: str, workspace: str, registry: dict):
    """E011: Cross-mount filesystem."""
    print("[recover] E011: Cross-mount filesystem detected.")
    print("[recover] Action: Clone repo to native filesystem and re-run from there.")
    print(f"[recover] Current path: {workspace}")
    result = subprocess.run(["df", "-P", "."], capture_output=True, text=True, cwd=workspace)
    print(f"[recover] Filesystem: {result.stdout}")


def recover_e012_stale_cache(task_id: str, workspace: str, registry: dict):
    """E012: Preflight cache stale."""
    print("[recover] E012: Preflight cache > 30 min old.")
    cache_path = os.path.join(workspace, ".hermes", "kanban", "preflight_cache.json")
    if os.path.exists(cache_path):
        os.remove(cache_path)
        print(f"[recover] Removed stale cache: {cache_path}")
    print("[recover] Orchestrator must re-run preflight before dispatching.")


def recover_profile_no_config(task_id: str, workspace: str, registry: dict):
    """PR001: Profile has no config.yaml."""
    print("[recover] PR001: Profile missing config.yaml.")
    print("[recover] Action: Copy config.yaml and .env from default profile.")
    print("[recover] See kanban-advanced:kanban-preflight §5 for detailed recovery steps.")


# ── Cascade triage ─────────────────────────────────────────────────────

def triage_cascade(recovery_dir: str, registry: dict):
    """Handle multi-failure cascade: pause all, triage, recover in dependency order."""
    print("[recover] CASCADE TRIAGE — multiple failures detected.")
    print("[recover] Order: environment → agent → governance infra → verify")

    state = load_recovery_state(recovery_dir)

    # 1. Pause all downstream cards
    result = subprocess.run(["hermes", "kanban", "list"], capture_output=True, text=True)
    downstream = []
    for line in result.stdout.split("\n"):
        parts = line.split()
        if parts and parts[0].startswith("t_"):
            status = line[1:2] if len(line) > 1 else ""
            tid = parts[0]
            if "ready" in line.lower() or "todo" in line.lower():
                downstream.append(tid)
                subprocess.run(["hermes", "kanban", "block", tid, "Cascade triage — paused"])

    print(f"[recover] Paused {len(downstream)} downstream cards.")

    # 2. Environmental failures first (E007, E008, E011, E012, PR001)
    # 3. Agent failures (E001-E006, E009, E010)
    # 4. Governance infra failures (E013, G001, G002)

    state["cascade_events"].append({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "paused_cards": downstream,
        "resolved": False,
    })
    save_recovery_state(recovery_dir, state)

    print("[recover] Triage complete. Fix failures in order: env → agent → governance.")
    print("[recover] After fixes, re-run evaluation chain to verify, then unblock downstream cards.")


# ── Recovery action map ────────────────────────────────────────────────

RECOVERY_MAP = {
    "E001_FILE_NOT_IN_DIFF": recover_e001_file_not_in_diff,
    "E002_UNLISTED_FILE_CHANGE": recover_e002_unlisted_change,
    "E003_TEST_FAILURE": recover_e003_test_failure,
    "E004_COMMIT_MISMATCH": recover_e004_commit_mismatch,
    "E006_ZERO_OUTPUT": recover_e006_zero_output,
    "E007_DISK_FULL": recover_e007_disk_full,
    "E009_PUSH_TO_DEVELOPMENT": recover_e009_push_to_development,
    "E011_CROSS_MOUNT_FILESYSTEM": recover_e011_cross_mount,
    "E012_STALE_PREFlight_CACHE": recover_e012_stale_cache,
    "PR001_PROFILE_NO_CONFIG": recover_profile_no_config,
}


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="kanban sad-path recovery")
    parser.add_argument("task_id", nargs="?", default="", help="Task ID to recover")
    parser.add_argument("error_code", nargs="?", default="", help="Error code to recover from")
    parser.add_argument("--cascade", action="store_true", help="Triage multi-failure cascade")
    parser.add_argument("--list", action="store_true", help="List all known recovery actions")
    parser.add_argument("--workspace", default=os.getcwd(), help="Repo root / worktree path")
    parser.add_argument("--registry", default="", help="Path to error-codes.yaml")
    parser.add_argument("--recovery-dir", default="", help="Recovery state directory")
    args = parser.parse_args()

    repo_root = args.workspace
    registry_path = args.registry or os.path.join(repo_root, "kanban-workflow", "registry", "error-codes.yaml")
    recovery_dir = args.recovery_dir or os.path.join(repo_root, ".hermes", "kanban", "recovery")

    registry = load_registry(registry_path)

    if args.list:
        print("Known recovery actions:")
        for code, fn in sorted(RECOVERY_MAP.items()):
            info = registry.get(code, {})
            desc = info.get("description", "?")
            sev = info.get("severity", "?")
            retry = "retryable" if info.get("retry") else "non-retryable"
            print(f"  {code:30s} [{sev:7s}] [{retry:14s}] {desc}")
        sys.exit(0)

    if args.cascade:
        triage_cascade(recovery_dir, registry)
        sys.exit(0)

    if not args.task_id or not args.error_code:
        parser.print_help()
        print("\nERROR: Pass task_id + error_code, --cascade, or --list.")
        sys.exit(1)

    # Single recovery
    error_code = args.error_code
    task_id = args.task_id

    info = registry.get(error_code, {})
    desc = info.get("description", error_code)
    rec = info.get("recovery", "See error registry for manual recovery steps.")

    print(f"[recover] Task: {task_id}")
    print(f"[recover] Error: {error_code} — {desc}")
    print(f"[recover] Recommended: {rec}")

    if error_code in RECOVERY_MAP:
        RECOVERY_MAP[error_code](task_id, repo_root, registry)
        log_recovery(recovery_dir, task_id, error_code, error_code, "recovered")
    else:
        print(f"[recover] No automated recovery for {error_code}. Manual intervention required.")
        print(f"[recover] Consult hermes-kanban-advanced-workflow/registry/error-codes.yaml for full recovery steps.")
        log_recovery(recovery_dir, task_id, error_code, "manual", "pending")
