"""Manage .worktreeinclude for kanban card worktrees."""

from __future__ import annotations

from pathlib import Path

from plugin.config_overlay import resolve_hermes_home

WORKTREE_INCLUDE_FILENAME = ".worktreeinclude"


def _normalize_include_line(line: str) -> str | None:
    stripped = line.split("#", 1)[0].strip()
    return stripped or None


def _is_under(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_worktree_include_paths(
    project_root: Path,
    hermes_home: Path | None = None,
) -> list[str]:
    """Return repo-relative paths to copy into card worktrees."""
    root = project_root.expanduser().resolve()
    hh = (hermes_home or resolve_hermes_home(root)).expanduser().resolve()
    paths: list[str] = [
        ".hermes/kanban-overrides/",
        ".hermes/kanban/memory/",
    ]

    hermes_dirs: list[Path] = []
    project_hermes = root / ".hermes"
    if project_hermes.is_dir():
        hermes_dirs.append(project_hermes)
    elif _is_under(root, hh):
        hermes_dirs.append(hh)

    for hermes_dir in hermes_dirs:
        rel_base = hermes_dir.relative_to(root).as_posix()
        scripts = hermes_dir / "scripts"
        if scripts.is_dir():
            paths.append(f"{rel_base}/scripts/")
            if (scripts / "lib").is_dir():
                paths.append(f"{rel_base}/scripts/lib/")
        plugin_scripts = hermes_dir / "plugins" / "kanban-advanced" / "scripts"
        if plugin_scripts.is_dir():
            rel_plugin = plugin_scripts.relative_to(root).as_posix()
            paths.append(f"{rel_plugin}/")
            plugin_lib = plugin_scripts / "lib"
            if plugin_lib.is_dir():
                paths.append(f"{plugin_lib.relative_to(root).as_posix()}/")

    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def ensure_worktreeinclude(
    project_root: Path,
    hermes_home: Path | None = None,
) -> list[str]:
    """Create or merge .worktreeinclude in the project repo root."""
    root = project_root.expanduser().resolve()
    required = resolve_worktree_include_paths(root, hermes_home)
    include_path = root / WORKTREE_INCLUDE_FILENAME

    existing: list[str] = []
    if include_path.is_file():
        for line in include_path.read_text(encoding="utf-8").splitlines():
            norm = _normalize_include_line(line)
            if norm:
                existing.append(norm)

    merged: list[str] = []
    seen: set[str] = set()
    for path in existing + required:
        if path not in seen:
            seen.add(path)
            merged.append(path)

    content = (
        "# Managed by kanban-advanced — gitignored paths for card worktrees\n"
        "# Copied by worktree_setup.sh (and Hermes -w when configured)\n"
        + "\n".join(merged)
        + "\n"
    )
    lines: list[str] = []
    if not include_path.is_file():
        include_path.write_text(content, encoding="utf-8")
        lines.append(f"   OK {include_path} ({len(merged)} paths)")
    elif include_path.read_text(encoding="utf-8") != content:
        include_path.write_text(content, encoding="utf-8")
        lines.append(f"   OK {include_path} updated ({len(merged)} paths)")
    else:
        lines.append(f"   OK {include_path} (up to date)")
    return lines
