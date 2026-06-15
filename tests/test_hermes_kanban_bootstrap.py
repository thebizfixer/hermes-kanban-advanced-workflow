"""Tests for Hermes kanban bootstrap config."""

from __future__ import annotations

import subprocess
import unittest

from plugin.hermes_kanban_bootstrap import (
    DISPATCH_STALE_TIMEOUT_SECONDS,
    apply_hermes_kanban_bootstrap_config,
)


class TestHermesKanbanBootstrap(unittest.TestCase):
    def test_apply_sets_auto_decompose_and_stale_timeout(self) -> None:
        calls: list[list[str]] = []
        logs: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        apply_hermes_kanban_bootstrap_config(fake_run, "hermes", log=logs.append)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ["hermes", "config", "set", "kanban.auto_decompose", "false"])
        self.assertEqual(
            calls[1],
            [
                "hermes",
                "config",
                "set",
                "kanban.dispatch_stale_timeout_seconds",
                DISPATCH_STALE_TIMEOUT_SECONDS,
            ],
        )
        self.assertTrue(any("auto_decompose" in line for line in logs))
        self.assertTrue(any("dispatch_stale_timeout_seconds" in line for line in logs))

    def test_apply_logs_manual_fix_on_failure(self) -> None:
        logs: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "error")

        apply_hermes_kanban_bootstrap_config(fake_run, "hermes", log=logs.append)

        self.assertTrue(any("set manually" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
