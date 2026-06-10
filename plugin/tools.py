"""Tool handlers — wrappers around `hermes kanban` CLI that return JSON.

Rules:
- Every handler takes a single ``args`` dict plus ``**kwargs`` — this matches how
  Hermes dispatches tools: ``tools/registry.py`` calls ``handler(args, **kwargs)``
  with the model-supplied parameters as one positional dict.
- Every handler MUST return a JSON string (json.dumps), never a raw dict.
- Errors MUST be returned as {"error": "message"}, never raised as exceptions.
- All CLI calls use subprocess.run with text=True and timeout.
"""

import json
import logging
import subprocess
import os

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
            encoding="utf-8",
            errors="replace",
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


def kanban_create(args: dict, **kwargs) -> str:
    """Create a new kanban card."""
    title = (args.get("title") or "").strip()
    if not title:
        return json.dumps({"error": "kanban_create requires a 'title'"})

    cli = ["create", title, "--json"]
    body = args.get("body")
    if body:
        cli.extend(["--body", body])
    assignee = args.get("assignee")
    if assignee:
        cli.extend(["--assignee", assignee])
    workspace = args.get("workspace")
    if workspace:
        cli.extend(["--workspace", workspace])
    branch = args.get("branch")
    if branch:
        cli.extend(["--branch", branch])
    for p in args.get("parents") or []:
        cli.extend(["--parent", str(p)])
    priority = args.get("priority")
    if priority is not None:
        cli.extend(["--priority", str(priority)])
    for s in args.get("skill") or []:
        cli.extend(["--skill", s])
    if args.get("goal"):
        cli.append("--goal")
    goal_max_turns = args.get("goal_max_turns")
    if goal_max_turns is not None:
        cli.extend(["--goal-max-turns", str(goal_max_turns)])

    return json.dumps(_run_kanban(cli))


def kanban_list(args: dict, **kwargs) -> str:
    """List cards on the board."""
    cli = ["list"]
    status = args.get("status")
    if status:
        cli.extend(["--status", status])
    assignee = args.get("assignee")
    if assignee:
        cli.extend(["--assignee", assignee])
    if args.get("json_output", True):
        cli.append("--json")
    return json.dumps(_run_kanban(cli))


def kanban_show(args: dict, **kwargs) -> str:
    """Show details for a specific card."""
    task_id = (args.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "kanban_show requires a 'task_id'"})
    cli = ["show", task_id]
    if args.get("json_output", True):
        cli.append("--json")
    return json.dumps(_run_kanban(cli))


def kanban_complete(args: dict, **kwargs) -> str:
    """Mark cards as completed."""
    task_ids = args.get("task_ids") or []
    summary = args.get("summary")
    if not task_ids or summary is None:
        return json.dumps({"error": "kanban_complete requires 'task_ids' and 'summary'"})
    cli = ["complete"] + [str(t) for t in task_ids]
    cli.extend(["--summary", summary])
    result = args.get("result")
    if result:
        cli.extend(["--result", result])
    return json.dumps(_run_kanban(cli))


def kanban_block(args: dict, **kwargs) -> str:
    """Block a card with a reason."""
    task_id = (args.get("task_id") or "").strip()
    reason = args.get("reason")
    if not task_id or not reason:
        return json.dumps({"error": "kanban_block requires 'task_id' and 'reason'"})
    cli = ["block", task_id, reason]
    return json.dumps(_run_kanban(cli))


def kanban_unblock(args: dict, **kwargs) -> str:
    """Unblock one or more cards."""
    task_ids = args.get("task_ids") or []
    if not task_ids:
        return json.dumps({"error": "kanban_unblock requires 'task_ids'"})
    cli = ["unblock"] + [str(t) for t in task_ids]
    reason = args.get("reason")
    if reason:
        cli.extend(["--reason", reason])
    return json.dumps(_run_kanban(cli))


def kanban_link(args: dict, **kwargs) -> str:
    """Link two cards as parent-child dependency."""
    parent_id = (args.get("parent_id") or "").strip()
    child_id = (args.get("child_id") or "").strip()
    if not parent_id or not child_id:
        return json.dumps({"error": "kanban_link requires 'parent_id' and 'child_id'"})
    cli = ["link", parent_id, child_id]
    return json.dumps(_run_kanban(cli))
