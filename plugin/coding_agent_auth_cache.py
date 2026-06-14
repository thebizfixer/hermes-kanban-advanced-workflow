"""Preflight coding-agent auth cache — shared by gate, workers, and invoke smoke."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

PREFLIGHT_CACHE_MAX_AGE_SECONDS = 30 * 60


def preflight_cache_path(project_root: Path | str | None = None) -> Path:
    root = Path(project_root or os.getcwd()).resolve()
    return root / ".hermes" / "kanban" / "preflight_cache.json"


def _parse_timestamp(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def read_preflight_cache(project_root: Path | str | None = None) -> dict | None:
    path = preflight_cache_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_preflight_cache_fresh(
    binary: str,
    project_root: Path | str | None = None,
    *,
    max_age_seconds: int = PREFLIGHT_CACHE_MAX_AGE_SECONDS,
) -> bool:
    data = read_preflight_cache(project_root)
    if not data:
        return False
    if str(data.get("coding_agent_binary", "")).strip() != binary:
        return False
    ts = _parse_timestamp(data.get("timestamp") or data.get("verified_at"))
    if ts is None:
        return False
    return (time.time() - ts) < max_age_seconds


def write_preflight_cache(
    binary: str,
    project_root: Path | str | None = None,
    *,
    source: str = "check_coding_agent_cli",
) -> Path:
    path = preflight_cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    payload = {
        "timestamp": now.isoformat(),
        "verified_at": now.timestamp(),
        "coding_agent_binary": binary,
        "source": source,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
