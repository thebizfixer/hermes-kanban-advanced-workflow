"""Tests for .worktreeinclude provisioning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.worktree_provision import (
    WORKTREE_INCLUDE_FILENAME,
    ensure_worktreeinclude,
    resolve_coding_agent_context_paths,
    resolve_worktree_include_paths,
)


class TestWorktreeProvision(unittest.TestCase):
    def test_resolve_paths_for_project_local_hermes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hermes = root / ".hermes"
            (hermes / "scripts" / "lib").mkdir(parents=True)
            (hermes / "kanban-overrides").mkdir(parents=True)
            (hermes / "kanban" / "memory").mkdir(parents=True)
            plugin_scripts = hermes / "plugins" / "kanban-advanced" / "scripts" / "lib"
            plugin_scripts.mkdir(parents=True)
            (plugin_scripts.parent / "coding_agent_invoke.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            (plugin_scripts / "coding_agent_env.sh").write_text("# env\n", encoding="utf-8")

            paths = resolve_worktree_include_paths(root, hermes)
            self.assertIn(".hermes/kanban-overrides/", paths)
            self.assertIn(".hermes/scripts/lib/", paths)
            self.assertIn(".hermes/plugins/kanban-advanced/scripts/lib/", paths)

    def test_resolve_paths_external_hermes_only_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".hermes" / "kanban-overrides").mkdir(parents=True)
            external = Path(tmp) / "external-hermes"
            external.mkdir()
            (external / "scripts").mkdir()

            paths = resolve_worktree_include_paths(root, external)
            self.assertIn(".hermes/kanban-overrides/", paths)
            self.assertNotIn(".hermes/scripts/", paths)

    def test_resolve_coding_agent_context_paths_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = root / ".cursor" / "rules"
            rules.mkdir(parents=True)
            (rules / "foo.mdc").write_text("rule", encoding="utf-8")
            paths = resolve_coding_agent_context_paths("agent", root)
            self.assertIn(".cursor/rules/", paths)

    def test_resolve_paths_includes_preflight_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".hermes" / "kanban-overrides").mkdir(parents=True)
            paths = resolve_worktree_include_paths(root, root / ".hermes")
            self.assertIn(".hermes/kanban/preflight_cache.json", paths)

    def test_ensure_worktreeinclude_creates_and_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".hermes" / "kanban-overrides").mkdir(parents=True)
            include = root / WORKTREE_INCLUDE_FILENAME
            include.write_text(".env\n", encoding="utf-8")

            lines = ensure_worktreeinclude(root, root / ".hermes")
            self.assertTrue(any("OK" in line for line in lines))
            content = include.read_text(encoding="utf-8")
            self.assertIn(".env", content)
            self.assertIn(".hermes/kanban-overrides/", content)


if __name__ == "__main__":
    unittest.main()
