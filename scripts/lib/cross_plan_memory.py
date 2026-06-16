#!/usr/bin/env python3
"""Cross-plan lesson store for postmortem → Optimize sad-path feedback."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_GLOBAL_LESSONS = 500
LESSON_KEY_FIELDS = ("failure_class", "subsystem", "pattern")


def memory_dir(repo_root: Path) -> Path:
    return repo_root / ".hermes" / "kanban" / "memory"


def global_path(repo_root: Path) -> Path:
    return memory_dir(repo_root) / "_global.json"


def lessons_jsonl_path(repo_root: Path) -> Path:
    return memory_dir(repo_root) / "lessons.jsonl"


def _lesson_key(lesson: dict[str, Any]) -> str:
    parts = [str(lesson.get(field, "")).strip().lower() for field in LESSON_KEY_FIELDS]
    return "|".join(parts)


def _read_global(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"lessons": [], "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"lessons": [], "updated_at": None}
    if not isinstance(data, dict):
        return {"lessons": [], "updated_at": None}
    lessons = data.get("lessons")
    if not isinstance(lessons, list):
        lessons = []
    return {"lessons": lessons, "updated_at": data.get("updated_at")}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _with_flock(path: Path, callback) -> Any:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lock_f:
        try:
            import fcntl

            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        return callback()


def append_lessons(repo_root: Path, new_lessons: list[dict[str, Any]]) -> int:
    """Merge lessons into _global.json (dedupe/cap) and append lessons.jsonl."""
    if not new_lessons:
        return 0

    gpath = global_path(repo_root)
    jpath = lessons_jsonl_path(repo_root)
    jpath.parent.mkdir(parents=True, exist_ok=True)

    stamped: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for raw in new_lessons:
        if not isinstance(raw, dict):
            continue
        lesson = dict(raw)
        lesson.setdefault("timestamp", now)
        stamped.append(lesson)

    with open(jpath, "a", encoding="utf-8") as handle:
        for lesson in stamped:
            handle.write(json.dumps(lesson, sort_keys=True) + "\n")

    def _merge() -> int:
        data = _read_global(gpath)
        existing = data.get("lessons") or []
        if not isinstance(existing, list):
            existing = []
        by_key: dict[str, dict[str, Any]] = {}
        for item in existing:
            if isinstance(item, dict):
                by_key[_lesson_key(item)] = item
        added = 0
        for lesson in stamped:
            key = _lesson_key(lesson)
            if key in by_key:
                prev = by_key[key]
                prev["last_seen"] = lesson.get("timestamp", now)
                prev["occurrences"] = int(prev.get("occurrences", 1)) + 1
                if lesson.get("plan_id"):
                    plans = prev.setdefault("plan_ids", [])
                    if isinstance(plans, list) and lesson["plan_id"] not in plans:
                        plans.append(lesson["plan_id"])
            else:
                entry = dict(lesson)
                entry["occurrences"] = 1
                entry["first_seen"] = lesson.get("timestamp", now)
                entry["last_seen"] = lesson.get("timestamp", now)
                entry["plan_ids"] = [lesson["plan_id"]] if lesson.get("plan_id") else []
                by_key[key] = entry
                added += 1
        merged = list(by_key.values())
        merged.sort(key=lambda x: str(x.get("last_seen", "")), reverse=True)
        merged = merged[:MAX_GLOBAL_LESSONS]
        payload = {
            "lessons": merged,
            "updated_at": now,
            "lesson_count": len(merged),
        }
        _atomic_write_json(gpath, payload)
        return added

    return _with_flock(gpath, _merge)


def lessons_from_kpi(kpi: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive cross-plan lesson rows from a postmortem KPI payload."""
    plan_id = str(kpi.get("plan_id", ""))
    lessons: list[dict[str, Any]] = []
    completeness = kpi.get("completeness") or {}
    for violation in completeness.get("violations") or []:
        if not isinstance(violation, dict):
            continue
        lessons.append(
            {
                "plan_id": plan_id,
                "failure_class": violation.get("kind", "completeness"),
                "subsystem": violation.get("caught_by", "unknown"),
                "pattern": _truncate_pattern(
                    violation.get("missed")
                    or violation.get("parent_task_id")
                    or violation.get("task_id")
                    or ""
                ),
                "source": "completeness_violation",
            }
        )
    for mode, count in (kpi.get("subsystem_failures") or {}).items():
        if count:
            lessons.append(
                {
                    "plan_id": plan_id,
                    "failure_class": str(mode),
                    "subsystem": "failure_mode",
                    "pattern": f"count={count}",
                    "source": "subsystem_failure",
                }
            )
    for task_id in kpi.get("thrash_outliers") or []:
        lessons.append(
            {
                "plan_id": plan_id,
                "failure_class": "thrash",
                "subsystem": "board_events",
                "pattern": str(task_id),
                "source": "thrash_outlier",
            }
        )
    if int(kpi.get("auth_escalation_count") or 0) > 0:
        lessons.append(
            {
                "plan_id": plan_id,
                "failure_class": "auth_error",
                "subsystem": "coding_agent",
                "pattern": f"count={kpi.get('auth_escalation_count')}",
                "source": "auth_escalation",
            }
        )
    return lessons


def record_plan_lessons(repo_root: Path, kpi: dict[str, Any]) -> int:
    return append_lessons(repo_root, lessons_from_kpi(kpi))


def _truncate_pattern(value: Any, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]
