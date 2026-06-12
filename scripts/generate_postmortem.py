#!/usr/bin/env python3
"""
Generate a kanban plan postmortem report in markdown.

Reads:
  - Token log JSONL ($KANBAN_TOKEN_LOG or ~/.hermes/kanban/tokens.jsonl)
  - Task history from the Hermes kanban SQLite DB ($KANBAN_DB or ~/.hermes/state.db)
  - Intervention counter (~/.hermes/kanban/logs/interventions.count)

Usage:
    python hermes-kanban-advanced-workflow/scripts/generate_postmortem.py --plan-id my-plan
    python hermes-kanban-advanced-workflow/scripts/generate_postmortem.py --plan-id my-plan --output .hermes/kanban/reports/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECTION_TITLES = (
    "Execution Summary",
    "Agent Performance",
    "Failure Taxonomy",
    "Intervention Log",
    "Discovered Pitfalls",
    "Skill Updates Needed",
    "Token Economics",
    "Learning Summary",
    "Operator Ground Truth (manual)",
)

FAILURE_KINDS = (
    "protocol_violation",
    "reclaimed",
    "timed_out",
    "crashed",
    "gave_up",
    "blocked",
    "iteration_budget",
    "ghost_task",
    "auth_error",
    "orchestrator_takeover",
)

PLAN_ID_RE = re.compile(r"^plan_id:\s*(\S+)", re.MULTILINE | re.IGNORECASE)


def _hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hermes"


def _project_root() -> Path:
    """Find the project root (where .hermes/kanban/ lives)."""
    # Try walking up from cwd to find .hermes/kanban/
    candidate = Path.cwd().resolve()
    for _ in range(6):
        if (candidate / ".hermes" / "kanban").is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Fallback: cwd
    return Path.cwd().resolve()


def _token_log_path() -> Path:
    env = os.environ.get("KANBAN_TOKEN_LOG", "").strip()
    if env:
        return Path(env).expanduser()
    return _project_root() / ".hermes" / "kanban" / "tokens.jsonl"


def _kanban_db_path() -> Path:
    env = os.environ.get("KANBAN_DB", "").strip()
    if env:
        return Path(env).expanduser()
    # Kanban tasks live in $HERMES_HOME/kanban.db, not ~/.hermes/state.db
    return _hermes_home() / "kanban.db"


def _interventions_count_path() -> Path:
    env = os.environ.get("KANBAN_INTERVENTIONS", "").strip()
    if env:
        return Path(env).expanduser()
    return _project_root() / ".hermes" / "kanban" / "logs" / "interventions.count"


def _interventions_log_path() -> Path:
    return _project_root() / ".hermes" / "kanban" / "logs" / "interventions.jsonl"


def _scope_violations_path() -> Path:
    return _project_root() / ".hermes" / "kanban" / "logs" / "scope_violations.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def read_intervention_count(path: Path) -> int:
    if not path.exists():
        return 0
    raw = path.read_text(encoding="utf-8", errors="replace")
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else 0


def format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _task_id_from_token(entry: dict[str, Any]) -> str:
    return str(
        entry.get("task_id")
        or entry.get("kanban_task_id")
        or entry.get("run_id")
        or "unknown"
    )


def _cursor_total(entry: dict[str, Any]) -> int:
    cursor = entry.get("cursor") or {}
    if isinstance(cursor, dict):
        total = cursor.get("total")
        if isinstance(total, (int, float)):
            return int(total)
        return int(
            (cursor.get("input_tokens") or 0)
            + (cursor.get("output_tokens") or 0)
            + (cursor.get("cache_read_tokens") or 0)
            + (cursor.get("cache_write_tokens") or 0)
        )
    return int(entry.get("estimated_total_tokens") or 0)


def _hermes_total(entry: dict[str, Any]) -> int:
    hermes = entry.get("hermes") or {}
    if isinstance(hermes, dict):
        total = hermes.get("total")
        if isinstance(total, (int, float)):
            return int(total)
        return int(
            (hermes.get("system_prompt_tokens") or 0)
            + (hermes.get("input_tokens") or 0)
            + (hermes.get("output_tokens") or 0)
        )
    return 0


def _duration_seconds(entry: dict[str, Any]) -> float:
    duration = entry.get("duration_seconds")
    if isinstance(duration, (int, float)):
        return float(duration)
    cursor = entry.get("cursor") or {}
    if isinstance(cursor, dict):
        ms = cursor.get("duration_ms")
        if isinstance(ms, (int, float)):
            return float(ms) / 1000.0
    return 0.0


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_ts(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass
class TaskEvent:
    kind: str
    summary: str = ""
    timestamp: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskRecord:
    task_id: str
    title: str = ""
    status: str = "unknown"
    profile: str = ""
    plan_id: str = ""
    body: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    events: list[TaskEvent] = field(default_factory=list)

    @property
    def failure_modes(self) -> list[str]:
        modes: list[str] = []
        for event in self.events:
            kind = event.kind.lower()
            if kind in FAILURE_KINDS:
                modes.append(kind)
            elif kind == "completed" and "protocol" in event.summary.lower():
                modes.append("protocol_violation")
            elif kind == "blocked" and "iteration" in event.summary.lower():
                modes.append("iteration_budget")
        if self.status in {"blocked", "crashed", "gave_up", "timed_out"}:
            if self.status not in modes:
                modes.append(self.status)
        return modes


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1]: row[2] for row in rows}


def _pick_column(columns: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    lower = {name.lower(): name for name in columns}
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    return None


def _row_value(row: sqlite3.Row, column: str | None, default: Any = "") -> Any:
    if not column:
        return default
    try:
        return row[column]
    except (IndexError, KeyError):
        return default


def _extract_plan_id(body: str, metadata: Any = None) -> str:
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = None
    if isinstance(metadata, dict):
        for key in ("plan_id", "planId", "plan"):
            value = metadata.get(key)
            if value:
                return str(value)
    match = PLAN_ID_RE.search(body or "")
    if match:
        return match.group(1)
    return ""


def _discover_task_table(conn: sqlite3.Connection) -> tuple[str, dict[str, str]] | None:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    preferred = ("kanban_tasks", "tasks", "kanban_task", "board_tasks")
    ordered = [t for t in preferred if t in tables] + [
        t for t in tables if t not in preferred
    ]
    for table in ordered:
        columns = _table_columns(conn, table)
        id_col = _pick_column(columns, ("id", "task_id", "uuid"))
        status_col = _pick_column(columns, ("status", "state", "phase"))
        if id_col and (status_col or "body" in {c.lower() for c in columns}):
            return table, columns
    return None


def _discover_event_table(conn: sqlite3.Connection) -> tuple[str, dict[str, str]] | None:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    preferred = ("kanban_events", "task_events", "events", "kanban_task_events")
    ordered = [t for t in preferred if t in tables] + [
        t for t in tables if t not in preferred
    ]
    for table in ordered:
        columns = _table_columns(conn, table)
        task_col = _pick_column(columns, ("task_id", "kanban_task_id", "card_id"))
        kind_col = _pick_column(
            columns, ("kind", "event_type", "type", "name", "outcome")
        )
        if task_col and kind_col:
            return table, columns
    return None


def load_plan_memory_task_ids(project_root: Path, plan_id: str) -> tuple[set[str] | None, str]:
    """Return task IDs from plan memory when available (strict postmortem scoping)."""
    candidates = [
        project_root / ".hermes" / "kanban" / "memory" / f"{plan_id}.json",
        _hermes_home() / "kanban" / "memory" / f"{plan_id}.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        raw_ids = data.get("task_ids")
        if isinstance(raw_ids, list) and raw_ids:
            return {str(item) for item in raw_ids}, f"scoped via plan memory task_ids (`{path}`)"
        by_key = data.get("task_ids_by_key")
        if isinstance(by_key, dict) and by_key:
            return {str(v) for v in by_key.values()}, f"scoped via plan memory task_ids_by_key (`{path}`)"
    return None, ""


def load_task_history(
    db_path: Path, plan_id: str, project_root: Path | None = None
) -> tuple[list[TaskRecord], list[str]]:
    notes: list[str] = []
    root = project_root or _project_root()
    task_id_filter, filter_note = load_plan_memory_task_ids(root, plan_id)
    if filter_note:
        notes.append(filter_note)
    elif not task_id_filter:
        notes.append(
            "No plan memory task_ids — falling back to exact plan_id match in metadata/body "
            "(substring plan_id match disabled)."
        )
    if not db_path.exists():
        notes.append(f"Kanban DB not found at `{db_path}` — task history inferred from token log only.")
        return [], notes

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        discovered = _discover_task_table(conn)
        if not discovered:
            notes.append(
                f"No kanban task table discovered in `{db_path}` — task history inferred from token log only."
            )
            return [], notes

        task_table, task_columns = discovered
        id_col = _pick_column(task_columns, ("id", "task_id", "uuid"))
        title_col = _pick_column(task_columns, ("title", "name", "summary"))
        status_col = _pick_column(task_columns, ("status", "state", "phase"))
        profile_col = _pick_column(task_columns, ("profile", "assignee", "owner"))
        body_col = _pick_column(task_columns, ("body", "description", "prompt"))
        plan_col = _pick_column(task_columns, ("plan_id", "plan"))
        meta_col = _pick_column(task_columns, ("metadata", "meta", "extra"))
        created_col = _pick_column(task_columns, ("created_at", "created", "created_ts"))
        updated_col = _pick_column(task_columns, ("updated_at", "updated", "updated_ts"))

        rows = conn.execute(f"SELECT * FROM {task_table}").fetchall()
        tasks: list[TaskRecord] = []
        for row in rows:
            body = str(_row_value(row, body_col, ""))
            metadata = _row_value(row, meta_col, None)
            row_plan = str(_row_value(row, plan_col, "") or _extract_plan_id(body, metadata))
            task_id = str(_row_value(row, id_col, "unknown"))
            if task_id_filter is not None:
                matched = task_id in task_id_filter
            else:
                matched = (
                    row_plan == plan_id
                    or bool(PLAN_ID_RE.search(body) and _extract_plan_id(body, metadata) == plan_id)
                )
            if not matched:
                continue

            task = TaskRecord(
                task_id=task_id,
                title=str(_row_value(row, title_col, "")),
                status=str(_row_value(row, status_col, "unknown") or "unknown"),
                profile=str(_row_value(row, profile_col, "")),
                plan_id=row_plan or plan_id,
                body=body,
                created_at=_parse_ts(_row_value(row, created_col, None)),
                updated_at=_parse_ts(_row_value(row, updated_col, None)),
            )
            tasks.append(task)

        event_discovered = _discover_event_table(conn)
        if event_discovered and tasks:
            event_table, event_columns = event_discovered
            task_col = _pick_column(event_columns, ("task_id", "kanban_task_id", "card_id"))
            kind_col = _pick_column(
                event_columns, ("kind", "event_type", "type", "name", "outcome")
            )
            summary_col = _pick_column(
                event_columns, ("summary", "message", "detail", "note", "payload")
            )
            ts_col = _pick_column(event_columns, ("timestamp", "created_at", "ts", "time"))

            task_ids = {task.task_id for task in tasks}
            placeholders = ",".join("?" for _ in task_ids)
            query = f"SELECT * FROM {event_table} WHERE {task_col} IN ({placeholders})"
            event_rows = conn.execute(query, tuple(task_ids)).fetchall()

            events_by_task: dict[str, list[TaskEvent]] = defaultdict(list)
            for event_row in event_rows:
                task_id = str(_row_value(event_row, task_col, ""))
                summary_raw = _row_value(event_row, summary_col, "")
                if isinstance(summary_raw, dict):
                    summary = json.dumps(summary_raw, sort_keys=True)
                else:
                    summary = str(summary_raw or "")
                events_by_task[task_id].append(
                    TaskEvent(
                        kind=str(_row_value(event_row, kind_col, "unknown")),
                        summary=summary,
                        timestamp=_parse_ts(_row_value(event_row, ts_col, None)),
                        raw=dict(event_row),
                    )
                )

            for task in tasks:
                task.events = sorted(
                    events_by_task.get(task.task_id, []),
                    key=lambda event: event.timestamp or datetime.min.replace(tzinfo=timezone.utc),
                )
        elif tasks:
            notes.append("No kanban event table discovered — failure taxonomy uses task status only.")

        if not tasks:
            notes.append(f"No tasks matched plan `{plan_id}` in `{db_path}`.")

        return tasks, notes
    finally:
        conn.close()


def _merge_tasks_with_tokens(
    tasks: list[TaskRecord], token_entries: list[dict[str, Any]], plan_id: str
) -> list[TaskRecord]:
    by_id = {task.task_id: task for task in tasks}
    for entry in token_entries:
        if entry.get("plan_id") and entry.get("plan_id") != plan_id:
            continue
        task_id = _task_id_from_token(entry)
        if task_id not in by_id:
            by_id[task_id] = TaskRecord(task_id=task_id, plan_id=plan_id, status="unknown")
    return list(by_id.values())


def _wall_clock_hours(tasks: list[TaskRecord]) -> float | None:
    timestamps: list[datetime] = []
    for task in tasks:
        for ts in (task.created_at, task.updated_at):
            if ts:
                timestamps.append(ts)
        for event in task.events:
            if event.timestamp:
                timestamps.append(event.timestamp)
    if len(timestamps) < 2:
        return None
    delta = max(timestamps) - min(timestamps)
    return round(delta.total_seconds() / 3600.0, 2)


def _classify_failure(task: TaskRecord) -> str | None:
    modes = task.failure_modes
    if modes:
        return modes[-1]
    status = task.status.lower()
    if status in {"done", "completed", "archived"}:
        return None
    if status in FAILURE_KINDS:
        return status
    if status not in {"", "unknown", "ready", "running", "todo"}:
        return status
    return None


def _pitfalls_from_data(
    tasks: list[TaskRecord],
    token_entries: list[dict[str, Any]],
    intervention_count: int,
) -> list[str]:
    pitfalls: list[str] = []
    failure_counter = Counter(
        mode for task in tasks if (mode := _classify_failure(task)) is not None
    )
    if failure_counter.get("protocol_violation"):
        pitfalls.append(
            "Protocol violations detected — workers exited without `kanban_complete`; "
            "verify every success path signals the board."
        )
    if failure_counter.get("reclaimed") or failure_counter.get("timed_out"):
        pitfalls.append(
            "Reclaim/time-out pattern observed — enforce heartbeat during long `agent -p` runs "
            "and prefer terminal commands for pipeline execution."
        )
    if failure_counter.get("iteration_budget"):
        pitfalls.append(
            "Iteration budget exhaustion — split large same-file cards or route heavy edits "
            "through orchestrator takeover with explicit file scope."
        )
    if intervention_count and len(tasks) and (intervention_count / len(tasks)) > 0.3:
        pitfalls.append(
            f"Intervention rate exceeded 30% ({intervention_count}/{len(tasks)}) — "
            "run mid-run reconciliation before resuming dispatch."
        )

    totals = [_cursor_total(entry) for entry in token_entries]
    if totals:
        avg = statistics.mean(totals)
        hot = [
            _task_id_from_token(entry)
            for entry in token_entries
            if _cursor_total(entry) > avg * 2
        ]
        if hot:
            pitfalls.append(
                f"High token burn on {len(hot)} task(s) (>2× plan average): "
                + ", ".join(sorted(set(hot))[:8])
                + (" …" if len(set(hot)) > 8 else "")
            )

    if not pitfalls:
        pitfalls.append("No automated pitfall signatures detected for this plan run.")
    return pitfalls


def _skill_updates(pitfalls: list[str]) -> list[str]:
    mapping = [
        ("protocol", "kanban-advanced:kanban-worker — enforce board signal on every code path; add post-agent verification SOP."),
        ("reclaim", "kanban-advanced:kanban-worker — heartbeat + hung-agent investigation at 300s; terminal for non-code tasks."),
        ("iteration budget", "kanban-advanced:kanban-orchestrator — split cards >200 lines / >2 files; cap same-file bundling."),
        ("intervention rate", "kanban-advanced:kanban-orchestrator — mid-run reconciliation checklist + SOUL.md integrity probe."),
        ("token burn", "kanban-advanced:kanban-reconciliation — token report review; flag >2× average tasks in KPI artifact."),
    ]
    updates: list[str] = []
    joined = " ".join(pitfalls).lower()
    for needle, recommendation in mapping:
        if needle in joined:
            updates.append(recommendation)
    if not updates:
        updates.append(
            "No skill updates flagged automatically — review reconciliation notes and codify any validated workflow changes."
        )
    return updates


def build_report(
    plan_id: str,
    tasks: list[TaskRecord],
    token_entries: list[dict[str, Any]],
    intervention_count: int,
    intervention_log: list[dict[str, Any]],
    scope_violations: list[dict[str, Any]],
    source_notes: list[str],
) -> str:
    plan_tokens = [entry for entry in token_entries if entry.get("plan_id") == plan_id]
    if not plan_tokens:
        plan_tokens = token_entries

    total_tasks = len(tasks) if tasks else len({ _task_id_from_token(e) for e in plan_tokens })
    completed = sum(
        1
        for task in tasks
        if task.status.lower() in {"done", "completed", "archived"}
    )
    failed = sum(
        1
        for task in tasks
        if task.status.lower() in {"crashed", "gave_up", "timed_out", "blocked"}
    )
    autonomous = completed
    takeovers = sum(
        1
        for task in tasks
        if any(mode in task.failure_modes for mode in ("orchestrator_takeover", "iteration_budget"))
        or "takeover" in task.body.lower()
    )
    if takeovers:
        autonomous = max(0, completed - takeovers)

    success_rate = (completed / total_tasks * 100.0) if total_tasks else 0.0
    intervention_rate = (intervention_count / total_tasks * 100.0) if total_tasks else 0.0
    duration_hours = _wall_clock_hours(tasks)

    cursor_total = sum(_cursor_total(entry) for entry in plan_tokens)
    hermes_total = sum(_hermes_total(entry) for entry in plan_tokens)
    cache_read = sum(
        int((entry.get("cursor") or {}).get("cache_read_tokens") or 0)
        for entry in plan_tokens
    )
    cache_input = sum(
        int((entry.get("cursor") or {}).get("input_tokens") or 0)
        for entry in plan_tokens
    )
    avg_task_tokens = (
        statistics.mean([_cursor_total(entry) for entry in plan_tokens])
        if plan_tokens
        else 0.0
    )

    failure_rows: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        mode = _classify_failure(task)
        if mode:
            failure_rows[mode].append(task.task_id)

    pitfalls = _pitfalls_from_data(tasks, plan_tokens, intervention_count)
    skill_updates = _skill_updates(pitfalls)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "---",
        f"plan_id: {plan_id}",
        f"generated_at: {generated_at}",
        "document_type: postmortem",
        "generator: hermes-kanban-advanced-workflow/scripts/generate_postmortem.py",
        "---",
        "",
        f"# Kanban Postmortem — {plan_id}",
        "",
    ]

    if source_notes:
        lines.extend(["> **Data notes:**"] + [f"> - {note}" for note in source_notes] + [""])

    # 1. Execution Summary
    lines.extend(
        [
            "## 1. Execution Summary",
            "",
            f"- **Plan:** `{plan_id}`",
            f"- **Generated:** {generated_at}",
            f"- **Tasks:** {total_tasks}",
            f"- **Completed:** {completed}",
            f"- **Failed / blocked:** {failed}",
            f"- **Autonomous completions:** {autonomous}",
            f"- **Orchestrator takeovers (est.):** {takeovers}",
            f"- **Success rate:** {success_rate:.1f}%",
            f"- **Intervention count:** {intervention_count}",
            f"- **Intervention rate:** {intervention_rate:.1f}%",
        ]
    )
    if duration_hours is not None:
        lines.append(f"- **Wall clock (from task timestamps):** ~{duration_hours}h")
    lines.append("")

    # 2. Agent Performance
    lines.extend(["## 2. Agent Performance", ""])
    if tasks:
        lines.extend(
            [
                "| Task | Status | Profile | Failure modes | Events |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for task in sorted(tasks, key=lambda item: item.task_id):
            modes = ", ".join(task.failure_modes) if task.failure_modes else "—"
            lines.append(
                f"| `{task.task_id}` | {task.status} | {task.profile or '—'} | {modes} | {len(task.events)} |"
            )
        lines.append("")
    else:
        lines.append("_No task rows loaded from kanban DB._")
        lines.append("")

    if plan_tokens:
        lines.extend(
            [
                "| Task | Model | Tokens | Duration | Status |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for entry in sorted(plan_tokens, key=lambda item: _task_id_from_token(item)):
            cursor = entry.get("cursor") or {}
            model = cursor.get("model") if isinstance(cursor, dict) else entry.get("model")
            lines.append(
                f"| `{_task_id_from_token(entry)}` | {model or '—'} | "
                f"{format_tokens(_cursor_total(entry))} | "
                f"{_duration_seconds(entry):.0f}s | {entry.get('status', '—')} |"
            )
        lines.append("")

    # Scope violations
    if scope_violations:
        total_reverted = sum(v.get("count", 0) for v in scope_violations)
        affected_cards = len(set(v.get("task_id", "") for v in scope_violations))
        lines.extend([
            "### Scope Violations",
            "",
            f"- **Cards affected:** {affected_cards}",
            f"- **Files reverted:** {total_reverted}",
            "",
            "| Task | Files reverted |",
            "| --- | --- |",
        ])
        for v in scope_violations:
            files = ", ".join(f"`{f}`" for f in v.get("files_reverted", []))
            lines.append(f"| `{v.get('task_id', '?')}` | {files} |")
        lines.append("")
    elif source_notes and any("scope" in n.lower() for n in source_notes):
        lines.append("_No scope violations recorded — E002 ran clean, or logging not yet active._")

    # Card learnings from plan memory completed_cards
    memory_dir = _project_root() / ".hermes" / "kanban" / "memory"
    memory_path = memory_dir / f"{plan_id}.json"
    if memory_path.is_file():
        try:
            memory_data = json.loads(memory_path.read_text(encoding="utf-8"))
            completed_cards = memory_data.get("completed_cards") or []
            if completed_cards:
                lines.extend(["### Card learnings", ""])
                for card in completed_cards:
                    title = card.get("title", card.get("task_id", "?"))
                    lines.append(f"- **{title}**")
                    for decision in card.get("decisions") or []:
                        lines.append(f"  - decision: {decision}")
                    for constraint in card.get("constraints") or []:
                        lines.append(f"  - constraint: {constraint}")
                    state_left = card.get("state_left")
                    if state_left:
                        lines.append(f"  - state: {state_left}")
                lines.append("")
        except (json.JSONDecodeError, OSError):
            pass
        lines.append("")

    # 3. Failure Taxonomy
    lines.extend(["## 3. Failure Taxonomy", ""])
    if failure_rows:
        lines.extend(["| Mode | Count | Tasks |", "| --- | ---: | --- |"])
        for mode, task_ids in sorted(failure_rows.items(), key=lambda item: (-len(item[1]), item[0])):
            lines.append(f"| {mode} | {len(task_ids)} | {', '.join(f'`{tid}`' for tid in task_ids)} |")
        lines.append("")
    else:
        lines.append("_No failure modes classified from task history._")
        lines.append("")

    # 4. Intervention Log
    lines.extend(["## 4. Intervention Log", ""])
    lines.append(f"- **Persistent counter:** `{intervention_count}` (`interventions.count`)")
    lines.append(f"- **Rate vs tasks:** {intervention_count}/{total_tasks} = {intervention_rate:.1f}%")
    lines.append("")
    if intervention_log:
        lines.append("| Timestamp | Task | Reason |")
        lines.append("| --- | --- | --- |")
        for entry in intervention_log:
            lines.append(
                f"| {entry.get('timestamp', '—')} | `{entry.get('task_id', '—')}` | "
                f"{entry.get('reason') or entry.get('summary') or entry.get('kind', '—')} |"
            )
        lines.append("")
    else:
        lines.append("_No structured intervention JSONL entries found — counter-only log._")
        lines.append("")

    # 5. Discovered Pitfalls
    lines.extend(["## 5. Discovered Pitfalls", ""])
    for item in pitfalls:
        lines.append(f"- {item}")
    lines.append("")

    # 6. Skill Updates Needed
    lines.extend(["## 6. Skill Updates Needed", ""])
    for item in skill_updates:
        lines.append(f"- {item}")
    lines.append("")

    # 7. Token Economics
    orchestrator_entries = [e for e in plan_tokens if e.get("source") == "orchestrator"]
    worker_entries = [e for e in plan_tokens if e.get("source") != "orchestrator"]
    orchestrator_total_tokens = sum(e.get("hermes", {}).get("total", 0) if isinstance(e.get("hermes"), dict) else e.get("hermes_total_tokens", 0) for e in orchestrator_entries)
    lines.extend(
        [
            "## 7. Token Economics",
            "",
            f"- **Cursor tokens (logged):** {format_tokens(cursor_total)} ({cursor_total:,})",
            f"- **Hermes worker tokens (logged):** {format_tokens(hermes_total)} ({hermes_total:,})",
            f"- **Orchestrator tokens (logged):** {format_tokens(orchestrator_total_tokens)} ({orchestrator_total_tokens:,})",
            f"- **Combined (logged):** {format_tokens(cursor_total + hermes_total + orchestrator_total_tokens)}",
            f"- **Per-task average (Cursor):** {format_tokens(int(avg_task_tokens))}",
        ]
    )
    if orchestrator_entries:
        lines.append(f"- **Orchestrator checkpoints logged:** {len(orchestrator_entries)} (planning, decompose, audit, cleanup)")
    if not orchestrator_entries:
        lines.append("- **⚠ Orchestrator tokens not logged** — orchestrator did not call log_orchestrator_tokens() at checkpoints. Sprint budgeting is blind to planning/audit overhead.")
    if cache_read or cache_input:
        cache_pct = (cache_read / (cache_read + cache_input) * 100.0) if (cache_read + cache_input) else 0.0
        lines.append(f"- **Cache read ratio:** {cache_pct:.1f}%")
    if plan_tokens and avg_task_tokens:
        hot_tasks = [
            _task_id_from_token(entry)
            for entry in plan_tokens
            if _cursor_total(entry) > avg_task_tokens * 2
        ]
        if hot_tasks:
            lines.append(
                "- **High-burn tasks (>2× avg):** "
                + ", ".join(f"`{task_id}`" for task_id in sorted(set(hot_tasks)))
            )
    lines.append("")

    # 8. Learning Summary
    lines.extend(
        [
            "## 8. Learning Summary",
            "",
            f"- Plan `{plan_id}` finished with **{success_rate:.1f}%** task success and "
            f"**{intervention_rate:.1f}%** intervention rate ({intervention_count} interventions).",
        ]
    )
    if source_notes:
        confidence = "high" if any("scoped via plan memory" in n for n in source_notes) else "medium"
        if any("inferred from token log only" in n for n in source_notes):
            confidence = "low"
        lines.append(f"- **Data confidence:** {confidence} — see Data notes at top of report.")
    if failure_rows:
        top_mode = max(failure_rows.items(), key=lambda item: len(item[1]))[0]
        lines.append(
            f"- Dominant failure mode: **{top_mode}** ({len(failure_rows[top_mode])} tasks) — "
            "address in the next plan's sad-path section and card granularity."
        )
    else:
        lines.append("- No dominant failure mode detected — preserve current card-body and monitoring patterns.")
    if cursor_total:
        lines.append(
            f"- Logged Cursor spend: **{format_tokens(cursor_total)}** tokens; "
            "feed into plan optimization line-budget and card split decisions."
        )
    lines.append(
        "- Read sections 5–6 before writing the next plan; update kanban skills when a pitfall repeats across runs."
    )
    lines.append("")
    lines.extend(
        [
            "## 9. Operator Ground Truth (manual)",
            "",
            "_Fill after the run — automated metrics can mis-count when plan memory or intervention JSONL is incomplete._",
            "",
            "- **Cards completed (operator):** _e.g. 12/12_",
            "- **Wall-clock hours:** _e.g. 3.5h_",
            "- **Manual intervention rate:** _e.g. 75% (6/8 impl cards)_",
            "- **Interventions (operator count):** _e.g. 11 vs automated counter_",
            "- **Notes:** _OAuth races, cron never ticked, salvage paths, etc._",
            "",
        ]
    )

    return "\n".join(lines)


def write_report(content: str, output: Path, plan_id: str) -> Path:
    if output.suffix == ".md":
        dest = output
    else:
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = output / f"{plan_id}_postmortem_{stamp}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate kanban plan postmortem markdown report")
    parser.add_argument("--plan-id", required=True, help="Plan identifier (matches plan_id in card bodies)")
    parser.add_argument(
        "--output",
        default=str(_hermes_home() / "kanban" / "reports"),
        help="Output directory or .md file path",
    )
    parser.add_argument("--token-log", type=Path, default=None, help="Override token JSONL path")
    parser.add_argument("--db", type=Path, default=None, help="Override kanban SQLite DB path")
    parser.add_argument(
        "--interventions",
        type=Path,
        default=None,
        help="Override interventions.count path",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print report to stdout in addition to writing the file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan_id = args.plan_id.strip()
    if not plan_id:
        print("error: --plan-id is required", file=sys.stderr)
        return 2

    token_path = args.token_log or _token_log_path()
    db_path = args.db or _kanban_db_path()
    interventions_path = args.interventions or _interventions_count_path()

    token_entries = read_jsonl(token_path)
    intervention_count = read_intervention_count(interventions_path)
    intervention_log = [
        entry
        for entry in read_jsonl(_interventions_log_path())
        if not entry.get("plan_id") or entry.get("plan_id") == plan_id
    ]
    scope_violations = read_jsonl(_scope_violations_path())

    source_notes: list[str] = []
    if not token_path.exists():
        source_notes.append(f"Token log missing at `{token_path}`.")
    if not interventions_path.exists():
        source_notes.append(f"Intervention counter missing at `{interventions_path}` (using 0).")
    if not intervention_log and intervention_count > 0:
        source_notes.append(f"Intervention JSONL missing — {intervention_count} intervention(s) occurred but no structured records written. Orchestrator did not call intervention logging.")
    if not scope_violations:
        source_notes.append("No scope violations logged — E002 ran without unlisted file changes, or scope violation logging not yet active for this plan.")

    tasks, db_notes = load_task_history(db_path, plan_id, _project_root())
    source_notes.extend(db_notes)
    tasks = _merge_tasks_with_tokens(tasks, token_entries, plan_id)

    report = build_report(
        plan_id=plan_id,
        tasks=tasks,
        token_entries=token_entries,
        intervention_count=intervention_count,
        intervention_log=intervention_log,
        scope_violations=scope_violations,
        source_notes=source_notes,
    )

    dest = write_report(report, Path(args.output), plan_id)
    print(f"Postmortem written: {dest}")
    if args.stdout:
        print()
        print(report)

    exit_code = 0
    for index, title in enumerate(SECTION_TITLES, start=1):
        needle = f"## {index}. {title}"
        if needle not in report:
            print(f"warning: missing section heading {needle!r}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
