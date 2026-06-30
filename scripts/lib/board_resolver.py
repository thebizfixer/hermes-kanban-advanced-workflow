"""Board resolver singleton — single source of truth for plan_id → board_slug resolution.

Every subsystem that queries kanban state should call resolve_board_for_plan()
instead of assuming "default".  This extracts the duplicated board-discovery logic
that was spread across 5 subsystems (lifecycle notify, token report, scope logging,
final audit, postmortem).

Discovery priority:
    1. HERMES_KANBAN_BOARD env var (explicit operator override)
    2. Live board whose slug starts with sanitized plan_id (most recent first)
    3. Archived board matching same prefix (most recent first)
    4. None — caller chooses fallback (usually "default")
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _sanitize_plan_id(plan_id: str) -> str:
    """Lowercase, replace non-alphanumeric with '-', trim to 48 chars."""
    sanitized = re.sub(r"[^a-z0-9-]", "-", plan_id.lower()).strip("-")
    return sanitized[:48]


def resolve_board_for_plan(
    plan_id: str,
    *,
    project_root: Path | None = None,
    hermes_home: Path | None = None,
) -> str | None:
    """Return the kanban board slug for a plan, or None if not found.

    Board names are timestamped: {sanitized_plan_id}-{YYYYMMDD}-{HHMMSS}.
    Matching is prefix-based: board slug must start with sanitized plan_id.
    """
    home = hermes_home or _hermes_home()
    sanitized = _sanitize_plan_id(plan_id)

    # Priority 1: explicit env override
    env_board = os.environ.get("HERMES_KANBAN_BOARD", "").strip()
    if env_board:
        return env_board

    # Priority 2: live boards (CLI or filesystem)
    live = _scan_live_boards(home, sanitized)
    if live:
        return live

    # Priority 3: archived boards
    archived = _scan_archived_boards(home, sanitized)
    if archived:
        return archived

    # Priority 4: not found
    return None


def _scan_live_boards(home: Path, sanitized: str) -> str | None:
    """Scan live boards matching sanitized plan_id prefix. Most recent first."""
    slugs: set[str] = set()

    # Try hermes CLI first
    try:
        result = subprocess.run(
            ["hermes", "kanban", "boards", "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    slug = parts[0].lstrip("●")
                    if slug.startswith(sanitized):
                        slugs.add(slug)
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Filesystem fallback
    boards_dir = home / "kanban" / "boards"
    if boards_dir.is_dir():
        for entry in boards_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(sanitized):
                db = entry / "kanban.db"
                if db.exists():
                    slugs.add(entry.name)

    return _pick_most_recent(slugs)


def _scan_archived_boards(home: Path, sanitized: str) -> str | None:
    """Scan archived boards matching sanitized plan_id prefix. Most recent first."""
    slugs: set[str] = set()
    archived_dir = home / "kanban" / "boards" / "_archived"
    if archived_dir.is_dir():
        for entry in archived_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(sanitized):
                db = entry / "kanban.db"
                if db.exists():
                    # Strip archive timestamp suffix to get original slug
                    # Archived names: {slug}-{unix_ts}
                    slug = entry.name
                    slugs.add(slug)
    return _pick_most_recent(slugs)


def _pick_most_recent(slugs: set[str]) -> str | None:
    """Pick the most recent slug by timestamp suffix. Returns None if empty."""
    if not slugs:
        return None
    # Sort by the timestamp portion (last 15 chars: YYYYMMDD-HHMMSS)
    # For archived slugs with unix timestamp suffix, sort by name length (longer = more recent)
    return sorted(slugs, reverse=True)[0]
