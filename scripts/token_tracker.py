#!/usr/bin/env python3
"""
Token tracker for kanban workers. Append one JSONL line per agent run.

Convenience wrapper (preferred for workers - fully neutral to coding_agent_binary):
    import sys; sys.path.insert(0, "/path/to/repo")
    from scripts.token_tracker import log_from_env
    log_from_env(plan_id="my-plan", turns=3, agent_input_tokens or via neutral "agent" section, ...)

Direct call:
    from scripts.token_tracker import log_token_run
    log_token_run(plan_id="my-plan", task_id="t_abc123", ...)

Read by scripts/kanban_token_report.py for reconciliation KPIs.

Log path: $KANBAN_TOKEN_LOG or default ~/.hermes/kanban/tokens.jsonl
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def get_coding_agent_binary() -> str:
    """Return the configured coding_agent_binary from project kanban-config.

    Priority:
    1. .hermes/kanban-overrides/kanban-config.yaml (project cwd first)
    2. $KANBAN_CODING_AGENT or $KANBAN_CODING_AGENT_BINARY env
    3. "hermes" (neutral default for this setup)
    """
    candidates = [
        Path.cwd() / ".hermes" / "kanban-overrides" / "kanban-config.yaml",
        Path.home() / ".hermes" / "kanban-overrides" / "kanban-config.yaml",
    ]
    for cfg in candidates:
        if cfg.exists():
            try:
                with open(cfg, encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("coding_agent_binary:"):
                            val = line.split(":", 1)[1].strip().strip("\"'")
                            if val:
                                return val
            except Exception:
                pass
    return (
        os.environ.get("KANBAN_CODING_AGENT")
        or os.environ.get("KANBAN_CODING_AGENT_BINARY")
        or "hermes"
    )


def get_agent_label(binary: str | None = None) -> str:
    b = (binary or get_coding_agent_binary()).lower()
    if "hermes" in b:
        return "hermes agent"
    if "cursor" in b:
        return "cursor agent"
    return f"{binary or 'agent'} agent"


def get_agent_section(binary: str | None = None) -> str:
    """Return the legacy token bucket key ('hermes' or 'cursor') for the binary."""
    b = (binary or get_coding_agent_binary()).lower()
    if "hermes" in b:
        return "hermes"
    return "cursor"


def _token_log_path() -> Path:
    """Resolve token log path from env or default.

    Priority:
    1. KANBAN_TOKEN_LOG env var
    2. Project-relative .hermes/kanban/tokens.jsonl (when running from a project with .hermes/)
    3. $HERMES_HOME/kanban/tokens.jsonl
    """
    env = os.environ.get("KANBAN_TOKEN_LOG", "")
    if env:
        return Path(env)
    # Check for project-relative path (same directory as postmortem reports)
    cwd = Path.cwd()
    project_log = cwd / ".hermes" / "kanban" / "tokens.jsonl"
    if project_log.parent.parent.exists():  # .hermes/ exists
        return project_log
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    return Path(hermes_home) / "kanban" / "tokens.jsonl"


def log_token_run(
    *,
    plan_id: str = "",
    task_id: str = "",
    run_id: str = "",
    cursor_input_tokens: int = 0,
    cursor_output_tokens: int = 0,
    cursor_cache_read_tokens: int = 0,
    cursor_cache_write_tokens: int = 0,
    cursor_model: str = "",
    hermes_turns: int = 0,
    hermes_model: str = "",
    hermes_total: int = 0,
    duration_seconds: float = 0.0,
    status: str = "completed",
    source: str = "agent",  # "agent" | "estimated" | "worker-direct" | "orchestrator-direct"
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one token record to the JSONL log."""
    estimate_total = hermes_total or (hermes_turns * 3000 if hermes_turns else 0)

    agent_binary = (
        os.environ.get("KANBAN_CODING_AGENT")
        or os.environ.get("KANBAN_CODING_AGENT_BINARY")
        or "hermes"
    )
    agent_total = (
        cursor_input_tokens + cursor_output_tokens +
        cursor_cache_read_tokens + cursor_cache_write_tokens
    ) or estimate_total

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plan_id": plan_id,
        "task_id": task_id,
        "run_id": run_id,
        "status": status,
        "source": source,
        "duration_seconds": duration_seconds,
        "agent": {
            "binary": get_coding_agent_binary(),
            "model": cursor_model or hermes_model,
            "total": agent_total,
        },
        "cursor": {
            "model": cursor_model,
            "input_tokens": cursor_input_tokens,
            "output_tokens": cursor_output_tokens,
            "cache_read_tokens": cursor_cache_read_tokens,
            "cache_write_tokens": cursor_cache_write_tokens,
            "total": (
                cursor_input_tokens + cursor_output_tokens +
                cursor_cache_read_tokens + cursor_cache_write_tokens
            ),
        },
        "hermes": {
            "model": hermes_model,
            "turns": hermes_turns,
            "total": estimate_total,
        },
    }
    if extra:
        record["extra"] = extra

    path = _token_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def log_from_env(
    *,
    plan_id: str = "",
    turns: int = 0,
    status: str = "completed",
    cursor_input_tokens: int = 0,
    cursor_output_tokens: int = 0,
    cursor_cache_read_tokens: int = 0,
    cursor_cache_write_tokens: int = 0,
    cursor_duration_ms: int = 0,
    source: str = "agent",
) -> str:
    """Convenience wrapper that reads task context from environment variables.

    Called by workers at task completion. Token fields for the configured coding_agent_binary come
    from parsing the agent's JSON stdout (usage.inputTokens etc.).
    """
    task_id = os.environ.get("HERMES_KANBAN_TASK", "")
    plan_id = plan_id or os.environ.get("HERMES_KANBAN_PLAN_ID", "")
    cursor_model = os.environ.get("HERMES_MODEL", "")
    hermes_model = os.environ.get("HERMES_MODEL", "")
    duration_seconds = cursor_duration_ms / 1000.0 if cursor_duration_ms else 0.0

    log_token_run(
        plan_id=plan_id,
        task_id=task_id,
        cursor_input_tokens=cursor_input_tokens,
        cursor_output_tokens=cursor_output_tokens,
        cursor_cache_read_tokens=cursor_cache_read_tokens,
        cursor_cache_write_tokens=cursor_cache_write_tokens,
        cursor_model=cursor_model,
        hermes_turns=turns,
        hermes_model=hermes_model,
        duration_seconds=duration_seconds,
        status=status,
        source=source,
    )

    return str(_token_log_path())


def log_from_agent_output(
    *,
    agent_output_json: str,
    plan_id: str = "",
    turns: int = 0,
    status: str = "completed",
) -> str:
    """Parse agent CLI JSON output and log exact token counts.

    Handles both Cursor CLI format (camelCase: inputTokens, outputTokens)
    and Claude Code format (snake_case: input_tokens, output_tokens).
    """
    data = json.loads(agent_output_json)
    usage = data.get("usage", {})

    return log_from_env(
        plan_id=plan_id,
        turns=turns,
        status=status,
        cursor_input_tokens=usage.get("inputTokens", usage.get("input_tokens", 0)),
        cursor_output_tokens=usage.get("outputTokens", usage.get("output_tokens", 0)),
        cursor_cache_read_tokens=usage.get("cacheReadTokens", usage.get("cache_read_tokens", 0)),
        cursor_cache_write_tokens=usage.get("cacheWriteTokens", usage.get("cache_write_tokens", 0)),
        cursor_duration_ms=data.get("duration_api_ms", data.get("duration_ms", 0)),
        source="agent",
    )


def log_orchestrator_tokens(
    *,
    plan_id: str,
    checkpoint: str,
    turns: int = 0,
    note: str = "",
) -> str:
    """Log orchestrator session tokens at a planning/audit/cleanup checkpoint.

    Called by the orchestrator profile at major plan milestones.
    Workers log their own tokens via log_from_env() at task completion.
    This function logs the orchestrator's own session overhead.

    Args:
        plan_id: Plan identifier (required).
        checkpoint: One of planning-complete, decompose-complete, audit-start,
                    cleanup-complete.
        turns: Estimated turn count for this session phase.
        note: Human-readable context (e.g., "Plan hardened, 13 agent blocks").
    """
    hermes_estimate = turns * 3000  # system prompt + tool schemas ≈ 3K/turn
    log_token_run(
        plan_id=plan_id,
        task_id="",  # orchestrator sessions aren't kanban tasks
        hermes_turns=turns,
        hermes_total=hermes_estimate,
        status=checkpoint,
        source="orchestrator",
        extra={"checkpoint": checkpoint, "note": note},
    )

    return str(_token_log_path())
