"""Tool handlers — wrappers around `hermes kanban` CLI that return JSON.

Rules:
- Every handler MUST return a JSON string (json.dumps), never a raw dict.
- Errors MUST be returned as {"error": "message"}, never raised as exceptions.
- All CLI calls use subprocess.run with text=True and timeout.
"""

import json
import logging
import subprocess
import os
from typing import Optional

logger = logging.getLogger(__name__)

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
DEFAULT_TIMEOUT = 30


def _run_kanban(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run a hermes kanban subcommand and return parsed JSON or error dict."""
    cmd = [HERMES_BIN, "kanban"] + args
    logger.debug("kanban tool: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or f"exit code {result.returncode}"}
        stdout = result.stdout.strip()
        if not stdout:
            return {"success": True}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"success": True, "output": stdout}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": f"hermes binary not found at '{HERMES_BIN}'"}
    except Exception as exc:
        return {"error": str(exc)}


def kanban_create(title: str, body: Optional[str] = None, assignee: Optional[str] = None,
                  workspace: Optional[str] = None, branch: Optional[str] = None,
                  parents: Optional[list] = None, priority: Optional[int] = None,
                  skill: Optional[list] = None, goal: bool = False,
                  goal_max_turns: Optional[int] = None) -> str:
    """Create a new kanban card."""
    args = ["create", title, "--json"]
    if body:
        args.extend(["--body", body])
    if assignee:
        args.extend(["--assignee", assignee])
    if workspace:
        args.extend(["--workspace", workspace])
    if branch:
        args.extend(["--branch", branch])
    if parents:
        for p in parents:
            args.extend(["--parent", str(p)])
    if priority is not None:
        args.extend(["--priority", str(priority)])
    if skill:
        for s in skill:
            args.extend(["--skill", s])
    if goal:
        args.append("--goal")
    if goal_max_turns is not None:
        args.extend(["--goal-max-turns", str(goal_max_turns)])

    return json.dumps(_run_kanban(args))


def kanban_list(status: Optional[str] = None, assignee: Optional[str] = None,
                json_output: bool = True) -> str:
    """List cards on the board."""
    args = ["list"]
    if status:
        args.extend(["--status", status])
    if assignee:
        args.extend(["--assignee", assignee])
    if json_output:
        args.append("--json")
    return json.dumps(_run_kanban(args))


def kanban_show(task_id: str, json_output: bool = True) -> str:
    """Show details for a specific card."""
    args = ["show", task_id]
    if json_output:
        args.append("--json")
    return json.dumps(_run_kanban(args))


def kanban_complete(task_ids: list[str], summary: str, result: Optional[str] = None) -> str:
    """Mark cards as completed."""
    args = ["complete"] + task_ids
    args.extend(["--summary", summary])
    if result:
        args.extend(["--result", result])
    return json.dumps(_run_kanban(args))


def kanban_block(task_id: str, reason: str) -> str:
    """Block a card with a reason."""
    args = ["block", task_id, reason]
    return json.dumps(_run_kanban(args))


def kanban_unblock(task_ids: list[str], reason: Optional[str] = None) -> str:
    """Unblock one or more cards."""
    args = ["unblock"] + task_ids
    if reason:
        args.extend(["--reason", reason])
    return json.dumps(_run_kanban(args))


def kanban_link(parent_id: str, child_id: str) -> str:
    """Link two cards as parent-child dependency."""
    args = ["link", parent_id, child_id]
    return json.dumps(_run_kanban(args))
