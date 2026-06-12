"""Agent-neutral plan file resolution for kanban gates and evaluation chain."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_PLAN_SEARCH_DIRS: tuple[str, ...] = (
    ".hermes/kanban/plans",
    ".agent/plans",
    ".cursor/plans",
    ".claude/plans",
    ".codex/plans",
    ".gemini/plans",
)

_GOVERNANCE_DOC_PREFIX = "docs/"


def _repo_root(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve()


def load_plan_search_dirs(repo_root: str | Path) -> List[str]:
    """Built-in defaults plus optional plan_search_dirs from kanban-config overlay."""
    root = _repo_root(repo_root)
    dirs = list(DEFAULT_PLAN_SEARCH_DIRS)
    overlay = root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if overlay.is_file():
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
            extra = data.get("plan_search_dirs") or []
            if isinstance(extra, list):
                for entry in extra:
                    if isinstance(entry, str) and entry.strip():
                        rel = entry.strip().replace("\\", "/").strip("/")
                        if rel and rel not in dirs:
                            dirs.append(rel)
        except Exception:
            pass
    return dirs


def _glob_plan_in_dir(directory: Path, plan_id: str) -> Optional[Path]:
    if not directory.is_dir():
        return None
    for pattern in (f"{plan_id}.plan.md", f"{plan_id}.md", f"*{plan_id}*.md"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def resolve_plan_file(
    repo_root: str | Path,
    plan_id: str,
    hint_path: str | None = None,
) -> Optional[Path]:
    """Resolve plan markdown to an existing file under repo_root."""
    root = _repo_root(repo_root)
    if hint_path:
        hint = Path(hint_path)
        if not hint.is_absolute():
            hint = root / hint
        if hint.is_file():
            return hint.resolve()

    search_dirs = load_plan_search_dirs(root)
    for rel in search_dirs:
        found = _glob_plan_in_dir(root / rel, plan_id)
        if found:
            return found.resolve()

    try:
        ls = subprocess.run(
            ["git", "ls-files", "--", "*/plans/*"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(root),
        )
        if ls.returncode == 0:
            for line in ls.stdout.splitlines():
                rel = line.strip().replace("\\", "/")
                if plan_id in rel and rel.endswith(".md"):
                    candidate = root / rel
                    if candidate.is_file():
                        return candidate.resolve()
    except Exception:
        pass
    return None


def is_governance_artifact_path(rel_path: str, repo_root: str | Path) -> bool:
    """True if path is under a registered plans dir or docs/ (E019 skip-list)."""
    norm = rel_path.replace("\\", "/").strip()
    if norm.startswith(_GOVERNANCE_DOC_PREFIX) or "/docs/" in norm:
        return True
    root = _repo_root(repo_root)
    search_dirs = load_plan_search_dirs(root)
    for d in search_dirs:
        prefix = d.rstrip("/") + "/"
        if norm.startswith(prefix) or f"/{prefix}" in norm:
            return True
        if norm.startswith(d.rstrip("/")):
            return True
    return "/plans/" in norm


def plan_file_committed(repo_root: str | Path, rel_path: str, branch: str) -> bool:
    """True if rel_path has at least one commit on branch."""
    root = _repo_root(repo_root)
    norm = rel_path.replace("\\", "/")
    result = subprocess.run(
        ["git", "log", "--oneline", "-1", branch, "--", norm],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
    )
    return result.returncode == 0 and bool(result.stdout.strip())
