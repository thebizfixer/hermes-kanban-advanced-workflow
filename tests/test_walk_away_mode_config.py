"""Tests for walk_away_mode config defaults."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.config_overlay import (
    DEFAULT_WALK_AWAY_MODE,
    build_overlay_yaml,
    normalize_walk_away_mode,
    resolve_walk_away_mode,
)


class TestWalkAwayModeConfig(unittest.TestCase):
    def test_default_is_false(self) -> None:
        self.assertFalse(DEFAULT_WALK_AWAY_MODE)
        self.assertFalse(normalize_walk_away_mode(None))

    def test_build_overlay_yaml_writes_walk_away_mode(self) -> None:
        yaml_text = build_overlay_yaml(
            working_branch="main",
            trigger_branch=None,
            coding_agent="agent",
            bundle_path="/tmp/plugin",
            hermes_home="/tmp/hermes",
        )
        self.assertIn("walk_away_mode: false", yaml_text)

    def test_normalize_true_values(self) -> None:
        self.assertTrue(normalize_walk_away_mode("true"))
        self.assertTrue(normalize_walk_away_mode("on"))

    def test_resolve_legacy_notify_on_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "notify_on_complete: true\n", encoding="utf-8"
            )
            self.assertTrue(resolve_walk_away_mode(root))

    def test_resolve_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(
                resolve_walk_away_mode(root, env={"WALK_AWAY_MODE": "true"})
            )


if __name__ == "__main__":
    unittest.main()
