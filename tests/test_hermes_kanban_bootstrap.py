"""Tests for Hermes kanban bootstrap config."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from plugin.hermes_kanban_bootstrap import (
    BLOCK_RECURRENCE_LIMIT_TARGET,
    DISPATCH_STALE_TIMEOUT_SECONDS,
    apply_hermes_kanban_bootstrap_config,
    patch_block_recurrence_limit,
)


class TestHermesKanbanBootstrap(unittest.TestCase):
    def test_apply_sets_config_keys(self) -> None:
        calls: list[list[str]] = []
        logs: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        apply_hermes_kanban_bootstrap_config(fake_run, "hermes", log=logs.append)

        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], ["hermes", "config", "set", "kanban.auto_decompose", "false"])
        self.assertEqual(
            calls[1],
            [
                "hermes", "config", "set",
                "kanban.dispatch_stale_timeout_seconds",
                DISPATCH_STALE_TIMEOUT_SECONDS,
            ],
        )
        self.assertEqual(calls[2][:4], ["hermes", "config", "set", "kanban.failure_limit"])
        self.assertTrue(any("auto_decompose" in line for line in logs))
        self.assertTrue(any("dispatch_stale_timeout_seconds" in line for line in logs))
        self.assertTrue(any("failure_limit" in line for line in logs))

    def test_apply_logs_manual_fix_on_failure(self) -> None:
        logs: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "error")

        apply_hermes_kanban_bootstrap_config(fake_run, "hermes", log=logs.append)

        self.assertTrue(any("set manually" in line for line in logs))

    def test_patch_block_recurrence_limit_already_correct(self) -> None:
        """Idempotent: reports OK when limit is already 5."""
        logs: list[str] = []
        content = "BLOCK_RECURRENCE_LIMIT = 5\nother = code"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            # Override HERMES_HOME so the function finds our temp file.
            # The function looks for <HERMES_HOME>/hermes-agent/hermes_cli/kanban_db.py
            # So we create the path structure under a temp dir.
            tmp_home = tempfile.mkdtemp()
            agent_dir = os.path.join(tmp_home, "hermes-agent", "hermes_cli")
            os.makedirs(agent_dir)
            target = os.path.join(agent_dir, "kanban_db.py")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)

            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": tmp_home}
            ):
                result = patch_block_recurrence_limit(log=logs.append)
        finally:
            os.unlink(target)
            os.rmdir(agent_dir)
            os.rmdir(os.path.dirname(agent_dir))
            os.rmdir(tmp_home)

        self.assertTrue(result)
        self.assertTrue(any("BLOCK_RECURRENCE_LIMIT = 5" in line for line in logs))

    def test_patch_block_recurrence_limit_needs_patching(self) -> None:
        """Patches from 2 to 5 when needed."""
        logs: list[str] = []
        content = "BLOCK_RECURRENCE_LIMIT = 2\nother = code"
        tmp_home = tempfile.mkdtemp()
        agent_dir = os.path.join(tmp_home, "hermes-agent", "hermes_cli")
        os.makedirs(agent_dir)
        target = os.path.join(agent_dir, "kanban_db.py")
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)

            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": tmp_home}
            ):
                result = patch_block_recurrence_limit(log=logs.append)
        finally:
            os.unlink(target)
            os.rmdir(agent_dir)
            os.rmdir(os.path.dirname(agent_dir))
            os.rmdir(tmp_home)

        self.assertTrue(result)
        self.assertTrue(any("patched" in line for line in logs))
        # Verify the file was actually patched
        with open(target, "r") as fh:
            self.assertIn("BLOCK_RECURRENCE_LIMIT = 5", fh.read())

    def test_patch_block_recurrence_limit_missing_file(self) -> None:
        """Graceful failure when kanban_db.py doesn't exist."""
        logs: list[str] = []
        tmp_home = tempfile.mkdtemp()
        # Don't create hermes-agent/hermes_cli/ — the file will be missing
        try:
            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": tmp_home}
            ):
                result = patch_block_recurrence_limit(log=logs.append)
        finally:
            os.rmdir(tmp_home)

        self.assertFalse(result)
        self.assertTrue(any("Could not find" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
