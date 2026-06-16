"""Unit tests for coding-agent runtime env and auth prerequisites."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plugin.coding_agent import _coding_agent_auth_lock_path
from plugin.coding_agent_env import (
    audit_coding_agent_prerequisites,
    dispatch_runtime_env_updates,
    ensure_coding_agent_runtime_env,
    is_home_unbound_error,
    resolve_runtime_home,
)


class TestCodingAgentEnv(unittest.TestCase):
    def test_resolve_runtime_home_from_home(self) -> None:
        self.assertEqual(resolve_runtime_home({"HOME": "/tmp/u"}), "/tmp/u")

    def test_resolve_runtime_home_from_userprofile(self) -> None:
        self.assertEqual(
            resolve_runtime_home({"USERPROFILE": "C:\\Users\\x"}),
            "C:\\Users\\x",
        )

    def test_ensure_sets_home_when_missing(self) -> None:
        with mock.patch("plugin.coding_agent_env.Path.home", return_value=Path("/resolved")):
            env = ensure_coding_agent_runtime_env({"PATH": "/bin"})
        self.assertEqual(Path(env["HOME"]), Path("/resolved"))

    def test_dispatch_runtime_env_updates(self) -> None:
        updates = dispatch_runtime_env_updates({"HOME": "/home/op"})
        self.assertEqual(updates["HOME"], "/home/op")

    def test_is_home_unbound_error(self) -> None:
        self.assertTrue(
            is_home_unbound_error("", "line 18: HOME: unbound variable")
        )
        self.assertFalse(is_home_unbound_error("ok", ""))

    def test_audit_grok_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issues = audit_coding_agent_prerequisites(
                "grok",
                {"HOME": tmp},
            )
        self.assertTrue(any("GROK_API_KEY" in issue for issue in issues))

    def test_audit_agent_missing_credential_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issues = audit_coding_agent_prerequisites(
                "agent",
                {"HOME": tmp},
            )
        self.assertTrue(any("credential file missing" in issue for issue in issues))

    def test_audit_passes_with_anthropic_key(self) -> None:
        issues = audit_coding_agent_prerequisites(
            "claude",
            {"HOME": "/tmp", "ANTHROPIC_API_KEY": "sk-test"},
        )
        self.assertEqual(issues, [])

    def test_auth_lock_path_under_hermes_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes = os.path.join(tmp, ".hermes")
            with mock.patch.dict(os.environ, {"HERMES_HOME": hermes}, clear=False):
                lock = _coding_agent_auth_lock_path()
            self.assertEqual(lock.parent.name, ".locks")
            self.assertTrue(str(lock).startswith(hermes))


if __name__ == "__main__":
    unittest.main()
