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
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# === NEUTRAL (driven by coding_agent_binary from config) ===
import os
from pathlib import Path as _P

def _get_coding_agent_binary():
    for base in (_P.cwd(), _P.home()):
        cfg = base / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
        if cfg.exists():
            try:
                with open(cfg, encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("coding_agent_binary:"):
                            val = line.split(":", 1)[1].strip().strip("\"'")
                            if val: return val
            except: pass
    return os.environ.get("KANBAN_CODING_AGENT") or "hermes"

def _get_agent_label():
    b = _get_coding_agent_binary().lower()
    if "hermes" in b: return "hermes agent"
    if "cursor" in b: return "cursor agent"
    return _get_coding_agent_binary() + " agent"

def _agent_total(entry):
    ag = entry.get("agent") or {}
    if ag.get("total") is not None: return int(ag["total"])
    binary = _get_coding_agent_binary()
    sec = "hermes" if "hermes" in binary.lower() else "cursor"
    s = entry.get(sec) or {}
    if s.get("total") is not None: return int(s["total"])
    return int((s.get("input_tokens") or 0) + (s.get("output_tokens") or 0) + (s.get("cache_read_tokens") or 0) + (s.get("cache_write_tokens") or 0) or entry.get("estimated_total_tokens") or 0)



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
OPEN_STATUSES = frozenset({"todo", "ready", "running", "blocked"})
TERMINAL_STATUSES = frozenset({"done", "completed", "archived"})
PARSER_MISS_CLASSES = frozenset({
    "acceptance_miss",
    "call_site_miss",
    "plan_file_zero_diff",
    "unplanned_change",
    "doc_coverage_gap",
})
PROCEDURAL_ACCEPTANCE_RE = re.compile(
    r"(?i)(done when|verify:|pytest|bash\s|python3?\s|\brg\b|hermes\s)",
)


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
    board = os.environ.get("HERMES_KANBAN_BOARD", "").strip()
    if board and board != "default":
        return _hermes_home() / "kanban" / "boards" / board / "kanban.db"
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


_RUN_BOUNDARY_STATUSES = frozenset({"planning-complete", "decompose-complete"})


def _scope_to_latest_run(
    entries: list[dict[str, Any]], plan_id: str
) -> list[dict[str, Any]]:
    """Filter token entries to only the most recent run for plan_id.

    Uses the most recent planning-complete checkpoint as the run boundary
    (it is the earliest checkpoint of a run). Falls back to decompose-complete
    if no planning-complete is found. If no boundary checkpoint is found,
    returns all entries (backward-compatible — pre-checkpoint runs are unscoped).
    """
    if not entries:
        return entries

    # Find the most recent planning-complete (preferred) and decompose-complete (fallback)
    planning_ts: str | None = None
    decompose_ts: str | None = None
    for entry in entries:
        status = str(entry.get("status") or entry.get("extra", {}).get("checkpoint", "")).strip()
        if status not in _RUN_BOUNDARY_STATUSES:
            continue
        ts = str(entry.get("timestamp") or "")
        if not ts:
            continue
        if status == "planning-complete":
            if planning_ts is None or ts > planning_ts:
                planning_ts = ts
        elif status == "decompose-complete":
            if decompose_ts is None or ts > decompose_ts:
                decompose_ts = ts

    boundary_ts = planning_ts or decompose_ts
    if boundary_ts is None:
        return entries  # No checkpoint found — return all (backward compatible)

    return [e for e in entries if str(e.get("timestamp") or "") >= boundary_ts]


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


def _agent_total(entry: dict[str, Any]) -> int:
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


def _classify_token_waste(entries: list[dict[str, Any]], total_tokens: int) -> dict[str, int]:
    """Classify token spend as necessary vs waste.
    
    Heuristic: first entry per unique (task_id, tests) = necessary;
    subsequent entries with same key = waste (re-loop).
    Orchestrator checkpoints = always necessary.
    """
    necessary = 0
    waste = 0
    seen: set[tuple[str, str]] = set()
    
    for entry in sorted(entries, key=lambda e: str(e.get("timestamp", ""))):
        tid = entry.get("task_id", "")
        tests = entry.get("tests_cmd", entry.get("tests", ""))
        source = entry.get("source", "")
        key = (tid, tests)
        
        if source == "orchestrator":
            necessary += _hermes_total(entry)
        elif key in seen:
            waste += _agent_total(entry) + _hermes_total(entry)
        else:
            necessary += _agent_total(entry) + _hermes_total(entry)
            seen.add(key)
    
    return {"necessary": necessary, "waste": waste}


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
    db_path: Path, plan_id: str, project_root: Path | None = None,
    board_task_ids: set[str] | None = None,
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
    if board_task_ids is not None:
        if not board_task_ids:
            notes.append("Board-scoped task ID set is empty — no tasks will be included.")
        else:
            notes.append(f"Board-scoped filtering active — restricting to {len(board_task_ids)} task ID(s) from board.")
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
                if task_id not in task_id_filter:
                    continue
                body_plan = _extract_plan_id(body, metadata)
                if body_plan and body_plan != plan_id:
                    continue
                matched = True
            else:
                matched = (
                    row_plan == plan_id
                    or bool(PLAN_ID_RE.search(body) and _extract_plan_id(body, metadata) == plan_id)
                )
            if not matched:
                continue

            # Board-scoped filtering: skip tasks not in the board's task list
            if board_task_ids is not None and task_id not in board_task_ids:
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
        else:
            archived_count = sum(1 for task in tasks if task.status.lower() == "archived")
            if archived_count == len(tasks):
                notes.append(
                    "All plan tasks are archived — metrics sourced from kanban.db (not active board list)."
                )
            elif archived_count:
                notes.append(
                    f"{archived_count} task(s) archived — postmortem metrics include archived rows from kanban.db."
                )

        return tasks, notes
    finally:
        conn.close()


def _merge_tasks_with_tokens(
    tasks: list[TaskRecord], token_entries: list[dict[str, Any]], plan_id: str
) -> list[TaskRecord]:
    by_id = {task.task_id: task for task in tasks}
    for entry in token_entries:
        entry_plan = str(entry.get("plan_id") or "").strip()
        if not entry_plan or entry_plan != plan_id:
            continue
        task_id = _task_id_from_token(entry)
        if task_id not in by_id:
            by_id[task_id] = TaskRecord(task_id=task_id, plan_id=plan_id, status="unknown")
    return list(by_id.values())


def _is_audit_task(task: TaskRecord) -> bool:
    if re.search(r"Type:\s*audit", task.body, re.IGNORECASE):
        return True
    return bool(re.search(r"final[ -]audit", task.title, re.IGNORECASE))


def _is_handoff_task(task: TaskRecord) -> bool:
    return (
        "orchestrator-handoff" in task.body
        or task.title.lower().startswith("decompose:")
    )


def _task_terminal_timestamp(task: TaskRecord) -> datetime | None:
    if task.status.lower() not in TERMINAL_STATUSES:
        return None
    if task.updated_at:
        return task.updated_at
    event_times = [e.timestamp for e in task.events if e.timestamp]
    return max(event_times) if event_times else None


def _wall_clock_hours(tasks: list[TaskRecord]) -> float | None:
    if not tasks:
        return None
    starts = [t.created_at for t in tasks if t.created_at]
    if not starts:
        return None
    run_start = min(starts)
    open_impl = [
        t
        for t in tasks
        if t.status.lower() in OPEN_STATUSES and not _is_handoff_task(t)
    ]
    if open_impl:
        end = datetime.now(timezone.utc)
    else:
        audit_ends = [
            ts
            for t in tasks
            if _is_audit_task(t)
            for ts in [_task_terminal_timestamp(t)]
            if ts is not None
        ]
        if audit_ends:
            end = max(audit_ends)
        else:
            terminal_ends = [
                ts
                for t in tasks
                if not _is_handoff_task(t)
                for ts in [_task_terminal_timestamp(t)]
                if ts is not None
            ]
            if not terminal_ends:
                return None
            end = max(terminal_ends)
    return round((end - run_start).total_seconds() / 3600.0, 2)


def _reblock_count(task: TaskRecord) -> int:
    return sum(1 for event in task.events if "block" in event.kind.lower())


def _count_parser_misses(
    tier1: dict[str, Any] | None, tier2: dict[str, Any] | None
) -> int:
    count = 0
    for payload in (tier1, tier2):
        if not payload:
            continue
        for violation in payload.get("violations") or []:
            if violation.get("class") in PARSER_MISS_CLASSES:
                count += 1
    return count


def _load_operational_context(project_root: Path, plan_id: str) -> dict[str, Any]:
    preflight_path = project_root / ".hermes" / "kanban" / "preflight_cache.json"
    preflight_failures: list[str] = []
    if preflight_path.is_file():
        try:
            data = json.loads(preflight_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, dict) and str(val.get("status", "")).lower() == "fail":
                        preflight_failures.append(str(key))
        except (json.JSONDecodeError, OSError):
            pass

    gateway_running = None
    try:
        result = subprocess.run(
            ["hermes", "gateway", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        gateway_running = result.returncode == 0 and "running" in (result.stdout or "").lower()
    except (OSError, subprocess.TimeoutExpired):
        gateway_running = False

    token_tracker_available = False
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
        from token_tracker_import import probe_token_tracker  # noqa: E402

        token_tracker_available = probe_token_tracker(project_root)
    except Exception:
        token_tracker_available = False

    return {
        "preflight_failures": preflight_failures,
        "gateway_running": gateway_running,
        "token_tracker_available": token_tracker_available,
    }


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
    plan_id: str = "",
    repo_root: Path | None = None,
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

    totals = [_agent_total(entry) for entry in token_entries]
    if totals:
        avg = statistics.mean(totals)
        hot = [
            _task_id_from_token(entry)
            for entry in token_entries
            if _agent_total(entry) > avg * 2
        ]
        if hot:
            pitfalls.append(
                f"High token burn on {len(hot)} task(s) (>2× plan average): "
                + ", ".join(sorted(set(hot))[:8])
                + (" …" if len(set(hot)) > 8 else "")
            )

    deploy_gap = _verification_deploy_attestation_gap(tasks, plan_id, repo_root)
    if deploy_gap:
        pitfalls.append(deploy_gap)

    presentation_gap = _presentation_false_completion_gap(tasks)
    if presentation_gap:
        pitfalls.append(presentation_gap)

    if not pitfalls:
        pitfalls.append("No automated pitfall signatures detected for this plan run.")
    return pitfalls


def _verification_deploy_attestation_gap(
    tasks: list[TaskRecord],
    plan_id: str,
    repo_root: Path | None,
) -> str | None:
    if not plan_id or repo_root is None:
        return None
    lib = Path(__file__).resolve().parent / "lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    try:
        from card_body import is_verification_deploy, parse_card_body
        from presentation_acceptance import verification_deploy_attested
    except ImportError:
        return None

    for task in tasks:
        if task.status.lower() not in TERMINAL_STATUSES:
            continue
        parsed = parse_card_body(task.body)
        if not is_verification_deploy(parsed, task.body):
            continue
        card_key = re.sub(
            r"[^a-z0-9]+",
            "-",
            (
                re.search(r"card_key:\s*(\S+)", task.body, re.I).group(1)
                if re.search(r"card_key:\s*(\S+)", task.body, re.I)
                else task.task_id
            ).lower(),
        ).strip("-")[:64]
        if verification_deploy_attested(repo_root, plan_id, card_key):
            continue
        return (
            "verification-deploy card(s) archived without per-card attestation JSON under "
            f"`.hermes/kanban/card-attestations/{plan_id}-{{card_key}}.json` — "
            "operator browser/deploy smoke was not recorded (false-completion risk)."
        )
    return None


def _presentation_false_completion_gap(tasks: list[TaskRecord]) -> str | None:
    """Detect layout-acceptance cards blocked on E028 during the run."""
    layout_cards = [
        t
        for t in tasks
        if "Acceptance (layout):" in t.body or "Acceptance (presentation):" in t.body
    ]
    if not layout_cards:
        return None
    blocked_e028 = []
    for task in layout_cards:
        for event in task.events:
            summary = (event.summary or "") + (event.kind or "")
            if "E028" in summary or "layout_acceptance" in summary.lower():
                blocked_e028.append(task.task_id)
                break
    if blocked_e028:
        return (
            f"{len(blocked_e028)} presentation-acceptance card(s) hit E028 — "
            "review DOM order / motion patterns before operator sign-off."
        )
    return None


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
    board_slug: str | None = None,
) -> str:
    plan_tokens = [entry for entry in token_entries if entry.get("plan_id") == plan_id]

    total_tasks = len(tasks) if tasks else len({_task_id_from_token(e) for e in plan_tokens})
    completed = sum(
        1
        for task in tasks
        if task.status.lower() in TERMINAL_STATUSES
    )
    failed = sum(1 for task in tasks if _classify_failure(task) is not None)
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

    agent_total = sum(_agent_total(entry) for entry in plan_tokens)
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
        statistics.mean([_agent_total(entry) for entry in plan_tokens])
        if plan_tokens
        else 0.0
    )

    failure_rows: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        mode = _classify_failure(task)
        if mode:
            failure_rows[mode].append(task.task_id)

    pitfalls = _pitfalls_from_data(
        tasks, plan_tokens, intervention_count, plan_id=plan_id, repo_root=_project_root()
    )
    skill_updates = _skill_updates(pitfalls)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    frontmatter_lines = [
        "---",
        f"plan_id: {plan_id}",
    ]
    if board_slug:
        frontmatter_lines.append(f"board_slug: {board_slug}")
    frontmatter_lines.extend([
        f"generated_at: {generated_at}",
        "document_type: postmortem",
        "generator: hermes-kanban-advanced-workflow/scripts/generate_postmortem.py",
        "---",
        "",
        f"# Kanban Postmortem — {plan_id}",
        "",
    ])
    lines: list[str] = frontmatter_lines

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
                f"{format_tokens(_agent_total(entry))} | "
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

    root = _project_root()
    tier1, tier2, audit_notes = _load_audit_tier_reports(plan_id, root)
    remediation_cards = [
        task.task_id
        for task in tasks
        if re.search(r"Type:\s*remediation", task.body, re.IGNORECASE)
    ]
    audit_fields = _audit_kpi_fields(
        tier1, tier2, remediation_cards, _audit_round_from_tasks(tasks)
    )
    if audit_notes or tier1 is not None or tier2 is not None:
        lines.extend(["### Final audit", ""])
        if audit_notes:
            for note in audit_notes:
                lines.append(f"- **{note}**")
        uncaught = audit_fields["uncaught_violation_count"]
        uncaught_display = "unknown" if uncaught is None else str(uncaught)
        lines.extend(
            [
                f"- **Final audit rounds:** {audit_fields['final_audit_rounds']}",
                f"- **Plan scope gaps (tier1):** {audit_fields['plan_scope_gaps']}",
                f"- **Doc coverage gaps (tier2):** {audit_fields['doc_coverage_gaps']}",
                f"- **Uncaught violations (goal 0):** {uncaught_display}",
                "",
            ]
        )

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

    label = _get_agent_label()
    # 7. Token Economics
    orchestrator_entries = [e for e in plan_tokens if e.get("source") == "orchestrator"]
    worker_entries = [e for e in plan_tokens if e.get("source") != "orchestrator"]
    orchestrator_total_tokens = sum(e.get("hermes", {}).get("total", 0) if isinstance(e.get("hermes"), dict) else e.get("hermes_total_tokens", 0) for e in orchestrator_entries)
    lines.extend(
        [
            "## 7. Token Economics",
            "",
            f"- **{_get_agent_label()} tokens (logged):** {format_tokens(agent_total)} ({agent_total:,})",
            f"- **Hermes worker tokens (logged):** {format_tokens(hermes_total)} ({hermes_total:,})",
            f"- **Orchestrator tokens (logged):** {format_tokens(orchestrator_total_tokens)} ({orchestrator_total_tokens:,})",
            f"- **Combined (logged):** {format_tokens(agent_total + hermes_total + orchestrator_total_tokens)}",
            f"- **Per-task average:** {format_tokens(int(avg_task_tokens))}",
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
            if _agent_total(entry) > avg_task_tokens * 2
        ]
        if hot_tasks:
            lines.append(
                "- **High-burn tasks (>2× avg):** "
                + ", ".join(f"`{task_id}`" for task_id in sorted(set(hot_tasks)))
            )
    lines.append("")

    # Waste breakdown
    if plan_tokens:
        classification = _classify_token_waste(plan_tokens, agent_total + hermes_total + orchestrator_total_tokens)
        n = classification["necessary"]
        w = classification["waste"]
        total_combined = n + w
        if total_combined > 0:
            ratio = w / total_combined * 100
            lines.extend([
                "- **Necessary spend:** " + format_tokens(n) + f" (first executions + checkpoints)",
                "- **Waste (re-loops):** " + format_tokens(w) + f" (repeated identical attempts)",
                f"- **Waste ratio:** {ratio:.1f}% (target: <20%)",
                "",
            ])
        else:
            lines.append("- **Waste breakdown unavailable** — no token entries to classify")

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
    if agent_total:
        lines.append(
            f"- Logged Cursor spend: **{format_tokens(agent_total)}** tokens; "
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


def _build_completeness_violations(
    tasks: list[TaskRecord],
    scope_violations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Return violations list plus worker/orchestrator catch counts."""
    violations: list[dict[str, Any]] = []
    for task in tasks:
        if not re.search(r"Type:\s*remediation", task.body, re.IGNORECASE):
            continue
        remediates = re.search(r"Remediates:\s*(\S+)", task.body, re.IGNORECASE)
        missed = re.search(r"Missed:\s*(.+?)(?:\n\n|\n(?:Type:|Files:|Acceptance:)|\Z)", task.body, re.IGNORECASE | re.DOTALL)
        violations.append(
            {
                "kind": "completeness_remediation",
                "remediation_task_id": task.task_id,
                "parent_task_id": remediates.group(1) if remediates else "",
                "missed": (missed.group(1).strip()[:500] if missed else ""),
                "caught_by": "orchestrator",
            }
        )
    for entry in scope_violations:
        if not isinstance(entry, dict):
            continue
        violations.append(
            {
                "kind": "scope_e002",
                "task_id": entry.get("task_id", ""),
                "count": entry.get("count", 0),
                "files": entry.get("files", []),
                "caught_by": "worker",
            }
        )
    worker_catch = sum(1 for v in violations if v.get("caught_by") == "worker")
    orchestrator_catch = sum(1 for v in violations if v.get("caught_by") == "orchestrator")
    return violations, worker_catch, orchestrator_catch


def _load_audit_tier_reports(plan_id: str, repo_root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Load tier1/tier2 audit JSON if present. Returns notes for missing files."""
    notes: list[str] = []
    report_dir = repo_root / ".hermes" / "kanban" / "reports"
    tier1: dict[str, Any] | None = None
    tier2: dict[str, Any] | None = None
    t1_path = report_dir / f"{plan_id}_audit_tier1.json"
    t2_path = report_dir / f"{plan_id}_audit_tier2.json"
    if t1_path.is_file():
        tier1 = json.loads(t1_path.read_text(encoding="utf-8"))
    else:
        notes.append(f"WARN: tier1 audit JSON missing at `{t1_path}` — uncaught_violation_count unknown")
    if t2_path.is_file():
        tier2 = json.loads(t2_path.read_text(encoding="utf-8"))
    else:
        notes.append(f"WARN: tier2 audit JSON missing at `{t2_path}` — doc coverage gaps unknown")
    return tier1, tier2, notes


def _audit_round_from_tasks(tasks: list[TaskRecord]) -> int:
    """Authoritative round counter lives on the audit card body (`Audit-round:`)."""
    for task in tasks:
        if not re.search(r"Type:\s*audit", task.body, re.IGNORECASE):
            continue
        match = re.search(r"(?m)^Audit-round:\s*(\d+)\s*$", task.body, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def _audit_kpi_fields(
    tier1: dict[str, Any] | None,
    tier2: dict[str, Any] | None,
    remediation_cards: list[str],
    audit_round_from_card: int = 0,
) -> dict[str, Any]:
    plan_scope_gaps = len((tier1 or {}).get("violations") or [])
    doc_coverage_gaps = len((tier2 or {}).get("violations") or [])
    parser_miss_count = _count_parser_misses(tier1, tier2)
    audit_round = audit_round_from_card
    if audit_round == 0:
        if tier1 and tier1.get("audit_round") is not None:
            audit_round = int(tier1["audit_round"])
        elif tier2 and tier2.get("audit_round") is not None:
            audit_round = int(tier2["audit_round"])
        elif (tier1 or tier2) and audit_round == 0:
            audit_round = 1

    if tier1 is None and tier2 is None:
        uncaught: int | None = None
    else:
        spawned = len(remediation_cards)
        total_gaps = plan_scope_gaps + doc_coverage_gaps
        uncaught = max(0, total_gaps - spawned - parser_miss_count) if total_gaps else 0

    return {
        "final_audit_rounds": audit_round,
        "plan_scope_gaps": plan_scope_gaps,
        "doc_coverage_gaps": doc_coverage_gaps,
        "parser_miss_count": parser_miss_count,
        "uncaught_violation_count": uncaught,
    }


def build_kpi_json(
    plan_id: str,
    tasks: list[TaskRecord],
    token_entries: list[dict[str, Any]],
    intervention_count: int,
    intervention_log: list[dict[str, Any]],
    scope_violations: list[dict[str, Any]],
    repo_root: Path | None = None,
    kpi_corrections: dict[str, Any] | None = None,
    board_slug: str | None = None,
) -> dict[str, Any]:
    """Machine-readable KPI artifact for dashboards and cross-run trend."""
    plan_tokens = [entry for entry in token_entries if entry.get("plan_id") == plan_id]

    total_tasks = len(tasks) if tasks else len({_task_id_from_token(e) for e in plan_tokens})
    completed = sum(
        1 for task in tasks if task.status.lower() in TERMINAL_STATUSES
    )
    failed = sum(1 for task in tasks if _classify_failure(task) is not None)
    takeovers = sum(
        1
        for task in tasks
        if any(mode in task.failure_modes for mode in ("orchestrator_takeover", "iteration_budget"))
        or "takeover" in task.body.lower()
    )
    autonomous = max(0, completed - takeovers) if takeovers else completed
    success_rate = (completed / total_tasks * 100.0) if total_tasks else 0.0
    intervention_rate = (intervention_count / total_tasks * 100.0) if total_tasks else 0.0
    duration_hours = _wall_clock_hours(tasks)

    failure_rows: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        mode = _classify_failure(task)
        if mode:
            failure_rows[mode].append(task.task_id)

    auth_escalations = len(failure_rows.get("auth_error", []))
    thrash_outliers = [
        {
            "task_id": task.task_id,
            "reblock_count": _reblock_count(task),
            "event_count": len(task.events),
        }
        for task in tasks
        if _reblock_count(task) >= 3
    ]

    agent_total = sum(_agent_total(entry) for entry in plan_tokens)
    cache_read = sum(int((entry.get("cursor") or {}).get("cache_read_tokens") or 0) for entry in plan_tokens)
    cache_input = sum(int((entry.get("cursor") or {}).get("input_tokens") or 0) for entry in plan_tokens)
    cache_ratio = (cache_read / cache_input) if cache_input else 0.0

    remediation_cards = [
        task.task_id
        for task in tasks
        if re.search(r"Type:\s*remediation", task.body, re.IGNORECASE)
    ]
    completeness_violations, worker_catch_count, orchestrator_catch_count = _build_completeness_violations(
        tasks, scope_violations
    )

    root = repo_root or _project_root()
    tier1, tier2, audit_notes = _load_audit_tier_reports(plan_id, root)
    audit_fields = _audit_kpi_fields(
        tier1, tier2, remediation_cards, _audit_round_from_tasks(tasks)
    )

    memory_ids, _ = load_plan_memory_task_ids(root, plan_id)
    known_ids = memory_ids or set()
    manual_interventions = [
        entry
        for entry in intervention_log
        if not entry.get("card_key")
        and str(entry.get("task_id") or "") not in known_ids
    ]
    operational = _load_operational_context(root, plan_id)
    log_lines = {
        task.task_id: len(task.events)
        for task in tasks
        if len(task.events) > 0
    }

    # New KPI enrichment fields (G1-G3, G6, G10)
    blocker_chain = _build_blocker_chain(tasks)
    deploy_state = _detect_deploy_state(tasks)
    completion_methods = Counter(
        _infer_completion_method(t) for t in tasks if t.status.lower() in TERMINAL_STATUSES
    )
    regression_check = _regression_check_failure_class(failure_rows)

    # Interventions: operator-observed placeholder (G2)
    # The automated counter is intervention_count; operator_observed is a seed
    # that the operator fills in during §9 Operator Ground Truth.
    operator_observed_interventions = intervention_count  # seed from counter
    # Check intervention log for any operator-authored entries
    for entry in intervention_log:
        if entry.get("source") == "operator" or entry.get("operator_override"):
            operator_observed_interventions = max(
                operator_observed_interventions, 
                len([e for e in intervention_log if e.get("source") == "operator"]),
            )
            break

    completion_method_breakdown: dict[str, int] = {
        "eval_chain": completion_methods.get("eval_chain", 0),
        "operator_cli": completion_methods.get("operator_cli", 0),
        "unknown": completion_methods.get("unknown", 0),
    }

    token_note = None
    if not plan_tokens:
        token_note = "No plan-scoped token rows — totals omitted (foreign rows excluded)."

    kpi: dict[str, Any] = {
        "plan_id": plan_id,
        "board_slug": board_slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "success_rate": round(success_rate, 2),
        "intervention_rate": round(intervention_rate, 2),
        "intervention_count": intervention_count,
        "first_pass_yield": round((autonomous / total_tasks * 100.0) if total_tasks else 0.0, 2),
        "autonomous_pct": round((autonomous / completed * 100.0) if completed else 0.0, 2),
        "total_tasks": total_tasks,
        "completed": completed,
        "failed": failed,
        "wall_clock_hours": duration_hours,
        "token_totals": {
            "cursor": agent_total,
            "cache_read": cache_read,
            "cache_input": cache_input,
            "cache_ratio": round(cache_ratio, 4),
            "source_note": token_note,
        },
        "subsystem_failures": {k: len(v) for k, v in failure_rows.items()},
        "auth_escalation_count": auth_escalations,
        "thrash_outliers": thrash_outliers,
        "completeness": {
            "violations": completeness_violations,
            "violation_count": len(completeness_violations),
            "remediation_cards_issued": len(remediation_cards),
            "remediation_task_ids": remediation_cards,
            "worker_catch_count": worker_catch_count,
            "orchestrator_catch_count": orchestrator_catch_count,
            "uncaught_violation_count": audit_fields["uncaught_violation_count"],
            "parser_miss_count": audit_fields["parser_miss_count"],
            "first_pass_clean_cards": max(0, completed - len(remediation_cards)),
        },
        "final_audit_rounds": audit_fields["final_audit_rounds"],
        "plan_scope_gaps": audit_fields["plan_scope_gaps"],
        "doc_coverage_gaps": audit_fields["doc_coverage_gaps"],
        "parser_miss_count": audit_fields["parser_miss_count"],
        "preflight_failures": operational["preflight_failures"],
        "gateway_running": operational["gateway_running"],
        "manual_interventions": manual_interventions,
        "log_lines": log_lines,
        "token_tracker_available": operational["token_tracker_available"],
        "audit_tier_notes": audit_notes,
        "scope_violations": len(scope_violations),
        "intervention_log_entries": len(intervention_log),
        "blocker_chain": blocker_chain,
        "deploy_state": deploy_state,
        "interventions_operator_observed": operator_observed_interventions,
        "completion_method": completion_method_breakdown,
        "regression_check": {
            "failure_class": regression_check,
            "description": (
                "test_drift — stale thresholds/SLO values, not logic bugs" if regression_check == "test_drift"
                else "logic_bug — production code fault" if regression_check == "logic_bug"
                else None
            ),
        },
    }
    token_coverage_pct = round(
        (len(plan_tokens) / completed * 100.0) if completed else 0.0, 2
    )
    uncaught = audit_fields["uncaught_violation_count"]
    if uncaught is None or token_coverage_pct < 50.0:
        data_confidence = "low"
    elif uncaught or token_coverage_pct < 80.0:
        data_confidence = "medium"
    else:
        data_confidence = "high"
    kpi["data_confidence"] = data_confidence
    kpi["token_coverage_pct"] = token_coverage_pct
    if kpi_corrections:
        for key in ("wall_clock_hours_corrected", "success_rate_corrected"):
            if key in kpi_corrections:
                kpi[key] = kpi_corrections[key]
        if kpi_corrections.get("_source"):
            kpi["correction_source"] = kpi_corrections["_source"]
    return kpi


def write_kpi_json(kpi: dict[str, Any], output: Path, plan_id: str) -> Path:
    if output.suffix == ".json":
        dest = output
    else:
        output.mkdir(parents=True, exist_ok=True)
        dest = output / f"{plan_id}_kpi.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(kpi, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)

    history = dest.parent / "kpi_history.jsonl"
    with open(history, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(kpi, sort_keys=True) + "\n")
    return dest


def _build_blocker_chain(
    tasks: list[TaskRecord],
) -> list[dict[str, Any]]:
    """G1 — Blocker chain for thrash outliers: eval code, Tests line, wait condition."""
    chains: list[dict[str, Any]] = []
    for task in tasks:
        reblocks = [e for e in task.events if "block" in e.kind.lower()]
        if len(reblocks) < 3:
            continue
        chain = {
            "task_id": task.task_id,
            "reblock_count": len(reblocks),
            "blocks": [],
        }
        for event in reblocks:
            summary = event.summary or ""
            # Extract error code and Tests line from block reason
            error_match = re.search(r"(E\d{3}[_\w]*)", summary)
            tests_match = re.search(r"Tests:\s*(\S[^\n]{0,120})", task.body, re.I)
            chain["blocks"].append({
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "error_code": error_match.group(1) if error_match else None,
                "reason_snippet": summary[:200],
            })
        if not chain["blocks"]:
            continue
        # Annotate with card's Tests line for context
        tests_line = ""
        for line in task.body.split("\n"):
            if line.strip().lower().startswith("tests:"):
                tests_line = line.strip()[6:].strip()[:200]
                break
        chain["tests_line"] = tests_line
        chains.append(chain)
    return chains


def _infer_completion_method(task: TaskRecord) -> str:
    """Infer how a completed task was marked done.
    
    Returns:
      - 'eval_chain' — last event before terminal was an eval chain ALLOW
      - 'operator_cli' — marked done via hermes kanban complete (operator CLI)
      - 'unknown' — can't determine from available events
    """
    if task.status.lower() not in TERMINAL_STATUSES:
        return "unknown"
    # Check last few events for eval chain signature
    for event in reversed(task.events[-10:]):
        summary = (event.summary or "").lower()
        if "evaluation chain" in summary or "eval chain" in summary:
            return "eval_chain"
        if "[chain] allow" in summary or "all checks passed" in summary:
            return "eval_chain"
        if event.kind.lower() in ("completed", "done", "archived"):
            raw = json.dumps(event.raw) if isinstance(event.raw, dict) else str(event.raw)
            if "evaluation chain" in raw.lower() or "eval_chain" in raw.lower():
                return "eval_chain"
    # If no eval chain signature found, assume operator CLI
    return "operator_cli" if task.events else "unknown"


def _detect_deploy_state(
    tasks: list[TaskRecord],
) -> dict[str, str] | None:
    """G3 — Detect deploy state from verification-deploy cards."""
    for task in tasks:
        deploy_match = re.search(r"(?m)^Deploy:\s*(.+)$", task.body, re.I)
        if deploy_match:
            parts = deploy_match.group(1).strip().split("-", 1)
            return {
                "service": parts[0].strip() if parts else "",
                "environment": parts[1].strip() if len(parts) > 1 else "unknown",
                "card_task_id": task.task_id,
                "card_status": task.status,
            }
    return None


def _regression_check_failure_class(failure_rows: dict[str, list[str]]) -> str | None:
    """Classify regression failures as test_drift or logic_bug from failure mode patterns."""
    if "test_failure" in {k.lower() for k in failure_rows}:
        return "test_drift"
    if any("test" in k.lower() or "e003" in k.lower() for k in failure_rows):
        return "test_drift"
    if failure_rows:
        return "logic_bug"
    return None


def build_reconciliation(
    plan_id: str,
    tasks: list[TaskRecord],
    token_entries: list[dict[str, Any]],
    intervention_count: int,
    scope_violations: list[dict[str, Any]],
    source_notes: list[str],
    board_slug: str | None = None,
) -> str:
    """Machinery-health reconciliation sidecar (separate from project-outcome postmortem).
    
    Focuses on plugin/agent health: evaluation chain stats, parser misses, thrash patterns,
    scope violations. Complements the project-outcome postmortem for operators tuning the
    kanban-advanced workflow itself.
    """
    plan_tokens = [e for e in token_entries if e.get("plan_id") == plan_id]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    recon_frontmatter = [
        "---",
        f"plan_id: {plan_id}",
    ]
    if board_slug:
        recon_frontmatter.append(f"board_slug: {board_slug}")
    recon_frontmatter.extend([
        f"generated_at: {generated_at}",
        "document_type: reconciliation",
        "generator: hermes-kanban-advanced-workflow/scripts/generate_postmortem.py",
        "---",
        "",
        f"# Reconciliation — {plan_id}",
        "",
    ])
    lines: list[str] = recon_frontmatter
    lines.extend([
        "> **Machinery-health report.** Focuses on plugin/agent evaluation chain performance,",
        "> parser misses, scope violations, and thrash patterns. For project outcomes",
        "> (what shipped, what didn't, acceptance gaps), see the postmortem companion.",
        "",
    ])

    if source_notes:
        lines.extend(["> **Data notes:**"] + [f"> - {note}" for note in source_notes] + [""])

    # 1. Evaluation chain stats
    total = len(tasks) if tasks else len({_task_id_from_token(e) for e in plan_tokens})
    completed = sum(1 for t in tasks if t.status.lower() in TERMINAL_STATUSES)
    completion_methods = Counter(_infer_completion_method(t) for t in tasks if t.status.lower() in TERMINAL_STATUSES)
    
    lines.extend([
        "## 1. Evaluation Chain Performance",
        "",
        f"- **Tasks processed:** {total}",
        f"- **Completed:** {completed}",
        f"- **Eval chain completions:** {completion_methods.get('eval_chain', 0)}",
        f"- **Operator CLI completions:** {completion_methods.get('operator_cli', 0)}",
        f"- **Unknown method:** {completion_methods.get('unknown', 0)}",
        "",
    ])

    # 2. Thrash analysis (blocker chain)
    thrash = _build_blocker_chain(tasks)
    if thrash:
        lines.extend(["## 2. Thrash Analysis (Blocker Chain)", ""])
        lines.extend(["| Task | Reblocks | Top error | Tests line |", "| --- | ---: | --- | --- |"])
        for chain in thrash[:10]:
            top_error = chain["blocks"][0]["error_code"] if chain["blocks"] else "?"
            tests = (chain.get("tests_line") or "?")[:80]
            lines.append(f"| `{chain['task_id']}` | {chain['reblock_count']} | {top_error} | {tests} |")
        lines.append("")

    # 3. Scope violations
    if scope_violations:
        total_reverted = sum(v.get("count", 0) for v in scope_violations)
        affected = len(set(v.get("task_id", "") for v in scope_violations))
        lines.extend([
            "## 3. Scope Violations",
            "",
            f"- **Cards affected:** {affected}",
            f"- **Files reverted:** {total_reverted}",
            "",
        ])
        lines.extend(["| Task | Files reverted |", "| --- | --- |"])
        for v in scope_violations[:20]:
            files = ", ".join(f"`{f}`" for f in v.get("files_reverted", [])[:5])
            lines.append(f"| `{v.get('task_id', '?')}` | {files} |")
        lines.append("")

    # 4. Completion method breakdown
    lines.extend([
        "## 4. Completion Method Breakdown",
        "",
        "| Task | Status | Method | Events |",
        "| --- | --- | --- | ---: |",
    ])
    for task in sorted(tasks, key=lambda t: t.task_id):
        if task.status.lower() not in TERMINAL_STATUSES:
            continue
        method = _infer_completion_method(task)
        lines.append(f"| `{task.task_id}` | {task.status} | {method} | {len(task.events)} |")
    lines.append("")

    # 5. Parser and audit health
    root = _project_root()
    tier1, tier2, audit_notes = _load_audit_tier_reports(plan_id, root)
    parser_miss_count = _count_parser_misses(tier1, tier2)
    lines.extend([
        "## 5. Parser & Audit Health",
        "",
        f"- **Parser misses (tier1+tier2):** {parser_miss_count}",
        f"- **Audit notes:** {len(audit_notes)}",
    ])
    for note in audit_notes[:10]:
        lines.append(f"  - {note}")
    if tier1:
        violations = tier1.get("violations") or []
        lines.append(f"- **Tier1 violations:** {len(violations)}")
    if tier2:
        violations = tier2.get("violations") or []
        lines.append(f"- **Tier2 violations:** {len(violations)}")
    lines.append("")

    return "\n".join(lines)


def write_reconciliation(content: str, output: Path, plan_id: str) -> Path:
    """Write reconciliation sidecar to reports directory."""
    if output.suffix == ".md":
        dest = output
    else:
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = output / f"{plan_id}_reconciliation_{stamp}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


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


def _board_db_path(board_slug: str) -> Path:
    """Return the kanban DB path for a specific board (live or archived)."""
    live = _hermes_home() / "kanban" / "boards" / board_slug / "kanban.db"
    if live.exists():
        # Only use live DB if it actually contains tasks (not cleared by archive)
        try:
            import sqlite3
            conn = sqlite3.connect(str(live))
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            conn.close()
            if count > 0:
                return live
        except Exception:
            pass
    # Search archived boards
    archived_dir = _hermes_home() / "kanban" / "boards" / "_archived"
    if archived_dir.is_dir():
        for entry in sorted(archived_dir.iterdir(), reverse=True):
            if entry.is_dir() and entry.name.startswith(board_slug):
                db = entry / "kanban.db"
                if db.exists():
                    return db
    return live  # fallback


def _read_task_ids_from_board_db(board_slug: str) -> set[str]:
    """Read task IDs directly from a board's kanban.db (live or archived)."""
    db_path = _board_db_path(board_slug)
    if not db_path.exists():
        return set()
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id FROM tasks").fetchall()
        conn.close()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def _get_board_task_ids(board_slug: str) -> tuple[set[str], list[str]]:
    """Run 'hermes kanban --board <slug> list --json' and return discovered task IDs.

    Returns (task_ids, notes) where task_ids is a set of task ID strings
    (empty if the command failed or the board has no tasks).
    Falls back to reading the board's kanban.db directly for archived boards.
    notes explain what happened.
    """
    notes: list[str] = []

    def _fallback_db() -> tuple[set[str], list[str]]:
        task_ids = _read_task_ids_from_board_db(board_slug)
        if task_ids:
            notes.append(f"Board '{board_slug}' — discovered {len(task_ids)} task ID(s) via archived DB.")
            return task_ids, notes
        return set(), notes

    try:
        result = subprocess.run(
            ["hermes", "kanban", "--board", board_slug, "list", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        notes.append(f"Failed to run 'hermes kanban --board {board_slug} list --json': {exc}")
        return _fallback_db()

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        notes.append(
            f"'hermes kanban --board {board_slug} list --json' exited with code {result.returncode}"
            + (f": {stderr}" if stderr else "")
        )
        return _fallback_db()

    stdout = (result.stdout or "").strip()
    if not stdout:
        notes.append(f"'hermes kanban --board {board_slug} list --json' produced no output — board may be empty.")
        return _fallback_db()

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        notes.append(f"Failed to parse JSON from 'hermes kanban --board {board_slug} list --json': {exc}")
        return _fallback_db()

    if isinstance(data, list):
        task_ids: set[str] = set()
        for item in data:
            if isinstance(item, dict):
                tid = item.get("id") or item.get("task_id") or item.get("uuid")
                if tid:
                    task_ids.add(str(tid))
        if not task_ids:
            notes.append(f"Board '{board_slug}' returned {len(data)} item(s) but no recognizable task IDs found.")
            return _fallback_db()
        else:
            notes.append(f"Board '{board_slug}' — discovered {len(task_ids)} task ID(s) via CLI.")
        return task_ids, notes

    if isinstance(data, dict):
        # Could be a wrapped response like {"tasks": [...]}
        for key in ("tasks", "items", "cards", "results"):
            items = data.get(key)
            if isinstance(items, list):
                task_ids = set()
                for item in items:
                    if isinstance(item, dict):
                        tid = item.get("id") or item.get("task_id") or item.get("uuid")
                        if tid:
                            task_ids.add(str(tid))
                if task_ids:
                    notes.append(f"Board '{board_slug}' — discovered {len(task_ids)} task ID(s) via CLI (key '{key}').")
                    return task_ids, notes
        notes.append(f"Board '{board_slug}' returned a JSON object but no recognizable task list found.")
        return set(), notes

    notes.append(f"Unexpected JSON type from 'hermes kanban --board {board_slug} list --json'.")
    return set(), notes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate kanban plan postmortem markdown report")
    parser.add_argument("--plan-id", required=True, help="Plan identifier (matches plan_id in card bodies)")
    parser.add_argument(
        "--board",
        default=None,
        help="Board slug for board-scoped filtering (runs 'hermes kanban --board <slug> list --json' to discover task IDs). "
             "When set, only tasks from this board are included in the report. Falls back to --plan-id behavior when omitted.",
    )
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

    board_slug = (args.board or "").strip() or None
    board_task_ids: set[str] | None = None
    board_notes: list[str] = []

    if board_slug:
        board_task_ids, board_notes = _get_board_task_ids(board_slug)
        if board_notes:
            for note in board_notes:
                print(f"board: {note}", file=sys.stderr)
        if board_task_ids is None:
            board_task_ids = set()

    token_path = args.token_log or _token_log_path()
    db_path = args.db or (board_slug and _board_db_path(board_slug)) or _kanban_db_path()
    interventions_path = args.interventions or _interventions_count_path()

    token_entries = [
        entry
        for entry in read_jsonl(token_path)
        if str(entry.get("plan_id") or "").strip() == plan_id
    ]
    # Also read from $HERMES_HOME/kanban/tokens.jsonl as secondary source
    # (orchestrator checkpoints pre-v5.5.2 wrote there; merge both)
    hermes_token_path = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "kanban" / "tokens.jsonl"
    if hermes_token_path.exists() and hermes_token_path.resolve() != token_path.resolve():
        hermes_entries = [
            entry
            for entry in read_jsonl(hermes_token_path)
            if str(entry.get("plan_id") or "").strip() == plan_id
        ]
        # Deduplicate by task_id + timestamp
        seen = {(e.get("task_id"), e.get("timestamp")) for e in token_entries}
        for entry in hermes_entries:
            key = (entry.get("task_id"), entry.get("timestamp"))
            if key not in seen:
                token_entries.append(entry)
                seen.add(key)

    # Board-scoped filtering: restrict token entries to board task IDs
    if board_task_ids is not None:
        token_entries = [
            e for e in token_entries
            if _task_id_from_token(e) in board_task_ids
        ]

    # Scope to most recent run only — avoids aggregating across multiple decompositions
    token_entries = _scope_to_latest_run(token_entries, plan_id)

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
    if board_notes:
        source_notes.extend(board_notes)

    tasks, db_notes = load_task_history(db_path, plan_id, _project_root(), board_task_ids=board_task_ids)
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
        board_slug=board_slug,
    )

    dest = write_report(report, Path(args.output), plan_id)
    kpi = build_kpi_json(
        plan_id=plan_id,
        tasks=tasks,
        token_entries=token_entries,
        intervention_count=intervention_count,
        intervention_log=intervention_log,
        scope_violations=scope_violations,
        repo_root=_project_root(),
        board_slug=board_slug,
    )
    kpi_dest = write_kpi_json(kpi, Path(args.output), plan_id)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
        import cross_plan_memory as cpm  # noqa: E402

        added = cpm.record_plan_lessons(_project_root(), kpi)
        if added:
            print(f"Cross-plan lessons updated: +{added} new pattern(s)")
    except Exception as exc:
        print(f"warning: cross-plan lesson write skipped: {exc}", file=sys.stderr)
    print(f"Postmortem written: {dest}")
    print(f"KPI JSON written: {kpi_dest}")

    # Reconciliation sidecar (machinery health)
    reconciliation = build_reconciliation(
        plan_id=plan_id,
        tasks=tasks,
        token_entries=token_entries,
        intervention_count=intervention_count,
        scope_violations=scope_violations,
        source_notes=source_notes,
        board_slug=board_slug,
    )
    recon_dest = write_reconciliation(reconciliation, Path(args.output), plan_id)
    print(f"Reconciliation written: {recon_dest}")

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
