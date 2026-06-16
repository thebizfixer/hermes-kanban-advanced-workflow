"""Manage .worktreeinclude for kanban card worktrees."""

from __future__ import annotations

import re
from pathlib import Path

from plugin.config_overlay import read_overlay_config, resolve_hermes_home

WORKTREE_INCLUDE_FILENAME = ".worktreeinclude"

# Per-binary project-context paths (existence-gated at merge time).
_CODING_AGENT_CONTEXT_CANDIDATES: dict[str, list[str]] = {
    "agent": [".cursor/rules/", ".cursor/skills/"],
    "claude": [
        "CLAUDE.md",
        ".claude/rules/",
        ".claude/skills/",
        ".claude/settings.json",
        ".mcp.json",
    ],
    "codex": ["AGENTS.md", "AGENTS.override.md", ".codex/rules/"],
    "gemini": ["GEMINI.md", ".gemini/skills/", ".agents/skills/"],
    "grok": ["AGENTS.md", "AGENTS.override.md", ".agents/skills/", ".grok/settings.json"],
    "aider": [".aider.conf.yml", "CONVENTIONS.md"],
}


def _normalize_include_line(line: str) -> str | None:
    stripped = line.split("#", 1)[0].strip()
    return stripped or None


def _is_under(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _aider_read_paths(project_root: Path) -> list[str]:
    """Expand aider read:/read-only: entries from .aider.conf.yml when present."""
    conf = project_root / ".aider.conf.yml"
    if not conf.is_file():
        return []
    try:
        text = conf.read_text(encoding="utf-8")
    except OSError:
        return []
    paths: list[str] = []
    for key in ("read:", "read-only:"):
        for match in re.finditer(rf"^{re.escape(key)}\s*(.+)$", text, re.MULTILINE):
            raw = match.group(1).strip()
            if raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1]
                for part in re.split(r",\s*", inner):
                    part = part.strip().strip("'\"")
                    if part and not part.startswith("*"):
                        paths.append(part)
            else:
                part = raw.strip("'\"")
                if part and not part.startswith("*"):
                    paths.append(part)
    return paths


def resolve_coding_agent_context_paths(
    binary: str,
    project_root: Path,
) -> list[str]:
    """Return repo-relative paths for the coding CLI's project context."""
    root = project_root.expanduser().resolve()
    candidates = list(_CODING_AGENT_CONTEXT_CANDIDATES.get(binary, []))
    if binary == "aider":
        candidates.extend(_aider_read_paths(root))

    resolved: list[str] = []
    seen: set[str] = set()
    for rel in candidates:
        path = root / rel
        if not path.exists():
            continue
        norm = rel if rel.endswith("/") or path.is_dir() else rel
        if norm not in seen:
            seen.add(norm)
            resolved.append(norm)
    return resolved


def resolve_worktree_include_paths(
    project_root: Path,
    hermes_home: Path | None = None,
    *,
    coding_agent_binary: str | None = None,
) -> list[str]:
    """Return repo-relative paths to copy into card worktrees."""
    root = project_root.expanduser().resolve()
    hh = (hermes_home or resolve_hermes_home(root)).expanduser().resolve()
    paths: list[str] = [
        ".hermes/kanban-overrides/",
        ".hermes/kanban/memory/",
        ".hermes/kanban/preflight_cache.json",
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

    binary = (coding_agent_binary or "").strip()
    if not binary:
        overlay = read_overlay_config(root)
        binary = str(overlay.get("coding_agent_binary", "agent")).strip() or "agent"
    paths.extend(resolve_coding_agent_context_paths(binary, root))

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
    *,
    coding_agent_binary: str | None = None,
) -> list[str]:
    """Create or merge .worktreeinclude in the project repo root."""
    root = project_root.expanduser().resolve()
    required = resolve_worktree_include_paths(
        root, hermes_home, coding_agent_binary=coding_agent_binary
    )
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
        binary_note = ""
        if coding_agent_binary:
            binary_note = f" for {coding_agent_binary}"
        elif any(p.startswith(".cursor/") or p.startswith(".claude/") for p in merged):
            binary_note = " (+coding-agent context)"
        lines.append(f"   OK {include_path} ({len(merged)} paths{binary_note})")
    elif include_path.read_text(encoding="utf-8") != content:
        include_path.write_text(content, encoding="utf-8")
        lines.append(f"   OK {include_path} updated ({len(merged)} paths)")
    else:
        lines.append(f"   OK {include_path} (up to date)")
    return lines
