"""Lifecycle hooks for the kanban-advanced plugin.

on_session_start — logs skill availability hint when a new session starts.
    Logger-only: text is NOT injected into agent context. Sad-path routing lives
    in SOUL prompts, procedural skill headers, and profile-local skills.

post_tool_call — logs board events after kanban tool calls (create, complete,
    block, unblock, link) for audit and debugging.
"""

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Path for board event log (JSONL)
EVENT_LOG_DIR = Path.home() / ".hermes" / "logs" / "kanban"
EVENT_LOG = EVENT_LOG_DIR / "board_events.jsonl"


def _ensure_log_dir():
    """Create the event log directory if it doesn't exist."""
    try:
        EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _get_profile(**kwargs: Any) -> str:
    """Best-effort detection of the active Hermes profile."""
    return os.environ.get("HERMES_PROFILE", "")


def on_session_start(**kwargs: Any) -> None:
    """Log skill availability hint.  Profile-aware for orchestrator vs default.

    The real discovery mechanism is materialized skills in
    <available_skills>.  This hook provides a logged breadcrumb and a
    best-effort hint when the CLI reference is available.
    """
    try:
        profile = _get_profile(**kwargs)

        if profile in ("orchestrator", "kanban-advanced-orchestrator"):
            skill_hint = (
                "[kanban-advanced] Orchestrator profile detected. "
                "Load kanban-advanced:kanban-orchestrator for the full "
                "decomposition SOP. On gate FAIL: kanban-advanced:kanban-orchestrator-governance "
                "+ skill_view(kanban-advanced, references/in-flight-governance-index.md). "
                "All kanban-advanced skills available: "
                "kanban-advanced:kanban-planning, "
                "kanban-advanced:kanban-preflight, "
                "kanban-advanced:kanban-cleanup, "
                "kanban-advanced:kanban-postmortem, "
                "kanban-advanced:kanban-reconciliation, "
                "kanban-advanced:kanban-notify."
            )
        elif profile in ("worker", "kanban-advanced-worker"):
            skill_hint = (
                "[kanban-advanced] Worker profile detected. "
                "Load kanban-advanced:kanban-worker for supervisor lifecycle. "
                "On DENY/block: kanban-advanced:kanban-worker-governance "
                "+ skill_view(kanban-advanced, references/in-flight-governance-index.md)."
            )
        else:
            skill_hint = (
                "[kanban-advanced] Plugin skills available. "
                "For plan work load kanban-advanced:kanban-planning. "
                "For full workflow load kanban-advanced:kanban-advanced. "
                "Execute/decompose needs orchestrator: prefer the board-mediated "
                "handoff — `python3 scripts/kanban_handoff.py --plan <plan.md>` "
                "(dispatcher runs kanban-advanced-orchestrator). Manual: "
                "`hermes -p kanban-advanced-orchestrator chat` (no-gateway fallback). "
                "Trigger phrases: 'plan this out', 'harden the plan', "
                "'optimize for kanban', 'execute the plan', "
                "'do a sanity check'."
            )

        logger.info("plugin: %s (profile=%s)", skill_hint, profile or "default")

    except Exception as exc:
        logger.error("plugin: on_session_start hook failed: %s", exc)


def post_tool_call(tool_name: str = "", args: Any = None, result: str = "",
                   task_id: str = "", duration_ms: int = 0, **kwargs: Any) -> None:
    """Log board events after kanban tool calls.

    Hermes invokes this via ``invoke_hook("post_tool_call", ...)`` with
    keyword arguments: ``tool_name``, ``args``, ``result``, ``task_id``,
    ``duration_ms``. The signature mirrors that contract exactly and accepts
    ``**kwargs`` for forward compatibility.

    Logs a JSONL entry for every kanban tool call, tracking what changed on the
    board. This enables postmortem analysis and audit trails.

    Note: Hermes catches all hook exceptions silently. We wrap in try/except to
    ensure logging failures don't cause silent data loss in the event stream.
    """
    kanban_tools = {
        "kanban_create", "kanban_list", "kanban_show",
        "kanban_complete", "kanban_block", "kanban_unblock", "kanban_link",
    }

    if tool_name not in kanban_tools:
        return

    try:
        _ensure_log_dir()

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "task_id": task_id or None,
            "duration_ms": duration_ms or None,
            "params": args,
            "result_snippet": str(result)[:500] if result else None,
        }

        with open(EVENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    except Exception as exc:
        # Hook errors are caught by Hermes, but we log to stderr as a fallback
        logger.error("plugin: post_tool_call hook failed for %s: %s", tool_name, exc)


def _get_board_status() -> str:
    """Get a quick summary of the current board state.

    Returns a short string suitable for session-start injection. Does NOT call
    hermes kanban (avoid blocking session start). Instead returns instructions
    for the operator to check manually.
    """
    return (
        "Run 'hermes kanban list --json' to see current board state. "
        "Run 'hermes kanban watch' for live event streaming."
    )
