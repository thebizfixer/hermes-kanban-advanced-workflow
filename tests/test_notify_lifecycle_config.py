"""Tests for notify_lifecycle config defaults."""

from __future__ import annotations

import unittest

from plugin.config_overlay import (
    DEFAULT_NOTIFY_LIFECYCLE,
    build_overlay_yaml,
    normalize_notify_lifecycle,
)


class TestNotifyLifecycleConfig(unittest.TestCase):
    def test_default_is_true(self) -> None:
        self.assertTrue(DEFAULT_NOTIFY_LIFECYCLE)
        self.assertTrue(normalize_notify_lifecycle(None))

    def test_build_overlay_yaml_writes_notify_lifecycle(self) -> None:
        yaml_text = build_overlay_yaml(
            working_branch="main",
            trigger_branch=None,
            coding_agent="agent",
            bundle_path="/tmp/plugin",
            hermes_home="/tmp/hermes",
        )
        self.assertIn("notify_lifecycle: true", yaml_text)

    def test_normalize_false_values(self) -> None:
        self.assertFalse(normalize_notify_lifecycle("false"))
        self.assertFalse(normalize_notify_lifecycle("off"))


if __name__ == "__main__":
    unittest.main()
