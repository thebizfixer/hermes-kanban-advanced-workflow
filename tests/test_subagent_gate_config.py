"""Tests for subagent_gate config defaults and overlay emission."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.config_overlay import (
    DEFAULT_SUBAGENT_GATE_ENABLED,
    _parse_subagent_gate_enabled_from_text,
    build_overlay_yaml,
    normalize_subagent_gate_enabled,
    overlay_path,
    resolve_subagent_gate_enabled,
)


class SubagentGateConfigTests(unittest.TestCase):
    def test_default_enabled_is_true(self) -> None:
        self.assertTrue(DEFAULT_SUBAGENT_GATE_ENABLED)
        self.assertTrue(normalize_subagent_gate_enabled(None))

    def test_parse_enabled_false_from_block(self) -> None:
        text = """
subagent_gate:
  enabled: false
  timeouts:
    plan_gate: 30
"""
        self.assertFalse(_parse_subagent_gate_enabled_from_text(text))

    def test_absent_block_returns_none(self) -> None:
        self.assertIsNone(_parse_subagent_gate_enabled_from_text("working_branch: main\n"))

    def test_resolve_defaults_true_without_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(resolve_subagent_gate_enabled(root))

    def test_resolve_respects_false_in_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            op = overlay_path(root)
            op.parent.mkdir(parents=True)
            op.write_text(
                "schema_version: \"1.0.0\"\n"
                "subagent_gate:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            self.assertFalse(resolve_subagent_gate_enabled(root))

    def test_build_overlay_yaml_writes_subagent_gate_enabled_true(self) -> None:
        yaml_text = build_overlay_yaml(
            working_branch="main",
            trigger_branch=None,
            coding_agent="agent",
            bundle_path="hermes-kanban-advanced-workflow",
            hermes_home="/home/user/.hermes",
        )
        self.assertIn("subagent_gate:", yaml_text)
        self.assertIn("enabled: true", yaml_text)
        self.assertIn("env_gate: 120", yaml_text)


if __name__ == "__main__":
    unittest.main()
