"""Import path helpers for scripts.token_tracker (orchestrator + postmortem)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def candidate_roots(project_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("HERMES_KANBAN_REPO_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    if project_root is not None:
        roots.append(project_root.resolve())
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    roots.append(hermes_home / "scripts")
    bundle = Path(__file__).resolve().parents[1]
    roots.append(bundle)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        ordered.append(root)
    return ordered


def ensure_token_tracker_import(project_root: Path | None = None) -> bool:
    for root in candidate_roots(project_root):
        if (root / "token_tracker.py").is_file():
            path = str(root)
            if path not in sys.path:
                sys.path.insert(0, path)
            return True
    return False


def probe_token_tracker(project_root: Path | None = None) -> bool:
    if not ensure_token_tracker_import(project_root):
        return False
    try:
        import token_tracker  # noqa: F401

        return hasattr(token_tracker, "log_orchestrator_tokens")
    except Exception:
        return False
