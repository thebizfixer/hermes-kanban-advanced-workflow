"""Tests for project root resolution when the plugin is a nested git clone."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.config_overlay import resolve_coding_agent, resolve_project_root


class TestResolveProjectRoot(unittest.TestCase):
    def test_overlay_wins_over_plugin_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "my-app"
            plugin = project / ".hermes" / "plugins" / "kanban-advanced"
            scripts = plugin / "scripts"
            scripts.mkdir(parents=True)
            (plugin / ".git").mkdir()
            overlay_dir = project / ".hermes" / "kanban-overrides"
            overlay_dir.mkdir(parents=True)
            (overlay_dir / "kanban-config.yaml").write_text(
                "coding_agent_binary: cursor-agent\n",
                encoding="utf-8",
            )

            resolved = resolve_project_root(start=scripts)
            self.assertEqual(resolved, project.resolve())
            self.assertEqual(resolve_coding_agent(resolved), "cursor-agent")

    def test_hermes_kanban_config_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "my-app"
            overlay_dir = project / ".hermes" / "kanban-overrides"
            overlay_dir.mkdir(parents=True)
            config = overlay_dir / "kanban-config.yaml"
            config.write_text(
                "coding_agent_binary: cursor-agent\n",
                encoding="utf-8",
            )
            import os

            prev = os.environ.get("HERMES_KANBAN_CONFIG")
            os.environ["HERMES_KANBAN_CONFIG"] = str(config)
            try:
                resolved = resolve_project_root()
                self.assertEqual(resolved, project.resolve())
            finally:
                if prev is None:
                    os.environ.pop("HERMES_KANBAN_CONFIG", None)
                else:
                    os.environ["HERMES_KANBAN_CONFIG"] = prev


if __name__ == "__main__":
    unittest.main()
