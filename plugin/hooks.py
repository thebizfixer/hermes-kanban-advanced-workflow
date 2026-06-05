"""Lifecycle hooks for the kanban-advanced plugin.

on_session_start — auto-loads the kanban-orchestrator skill when a new session
    starts for the orchestrator profile.

post_tool_call — logs board events after kanban tool calls (create, complete,
    block, unblock, link) for audit and debugging.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

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


def on_session_start(session_ctx):
    """Auto-load the kanban-orchestrator skill for the orchestrator profile.

    Fires once when a brand-new session is created. Does NOT fire on session
    continuation (second message in an existing session).

    The orchestrator skill provides board management SOPs, autonomous monitoring,
    and the decomposition protocol.
    """
    try:
        # Check if this session belongs to the orchestrator profile.
        # The orchestrator profile name is configurable — default is 'orchestrator'.
        profile = getattr(session_ctx, "profile", None) or ""
        orchestrator_names = {"orchestrator"}
        if not any(name in str(profile).lower() for name in orchestrator_names):
            return

        # Inject the orchestrator skill context
        board_status = _get_board_status()
        skill_hint = (
            "[kanban-advanced] Board status at session start:\n"
            f"{board_status}\n\n"
            "The kanban-orchestrator skill (plugin:kanban-orchestrator) is available "
            "for board management. Use skill_view('plugin:kanban-orchestrator') to "
            "load the full SOP."
        )
        try:
            session_ctx.inject_message(skill_hint, role="system")
        except AttributeError:
            # inject_message may not be available in all Hermes versions
            logger.debug("plugin: inject_message not available, logging board status instead")
            logger.info("plugin: board status at session start:\n%s", board_status)

    except Exception as exc:
        logger.error("plugin: on_session_start hook failed: %s", exc)


def post_tool_call(tool_name: str, params: dict, result: str):
    """Log board events after kanban tool calls.

    Signature: callback(tool_name: str, params: dict, result: str)

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
            "params": params,
            "result_snippet": str(result)[:500] if result else None,
        }

        with open(EVENT_LOG, "a") as f:
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
