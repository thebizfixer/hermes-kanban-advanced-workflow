"""Tests for lifecycle cron deliver resolver."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.config_overlay import normalize_notify_deliver  # noqa: E402
from plugin.hermes_notify_deliver import resolve_notify_deliver  # noqa: E402


class TestNotifyDeliver(unittest.TestCase):
    def test_overlay_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "notify_deliver: discord\n",
                encoding="utf-8",
            )
            self.assertEqual(resolve_notify_deliver(root), "discord")

    def test_single_home_channel_env(self) -> None:
        with mock.patch.dict(os.environ, {"DISCORD_HOME_CHANNEL": "#ops"}, clear=False):
            self.assertEqual(resolve_notify_deliver(None), "discord")

    def test_defaults_to_all_when_multiple_or_none(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.endswith("_HOME_CHANNEL")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_notify_deliver(None), "all")

    def test_normalize_notify_deliver_clears_auto(self) -> None:
        self.assertIsNone(normalize_notify_deliver(""))
        self.assertIsNone(normalize_notify_deliver("auto"))
        self.assertEqual(normalize_notify_deliver("discord"), "discord")


if __name__ == "__main__":
    unittest.main()
