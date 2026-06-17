"""Unit tests for coding-agent CLI adapters."""

from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugin.coding_agent import (
    CODING_AGENT_MODEL_AUTO,
    CONTESTED_AGENT_LABEL,
    _agent_smoke_json_unsupported,
    _interpret_smoke_result,
    build_dispatch_argv,
    build_smoke_argv,
    describe_smoke_failure,
    get_available_coding_binaries,
    is_auto_model,
    is_contested_binary_name,
    normalize_coding_agent_model,
    parse_cursor_list_models,
    resolve_adapter,
    smoke_test_coding_agent,
)


class TestCodingAgentHelpers(unittest.TestCase):
    def test_normalize_auto_sentinels(self) -> None:
        self.assertEqual(normalize_coding_agent_model(None), CODING_AGENT_MODEL_AUTO)
        self.assertEqual(normalize_coding_agent_model(""), CODING_AGENT_MODEL_AUTO)
        self.assertEqual(normalize_coding_agent_model("default"), CODING_AGENT_MODEL_AUTO)
        self.assertEqual(normalize_coding_agent_model("composer-2.5"), "composer-2.5")

    def test_is_auto_model(self) -> None:
        self.assertTrue(is_auto_model("auto"))
        self.assertTrue(is_auto_model("DEFAULT"))
        self.assertFalse(is_auto_model("gpt-5.2"))

    def test_parse_cursor_list_models(self) -> None:
        stdout = """Available models

auto - Auto
composer-2.5 - Composer 2.5 (current)
gpt-5.2 - GPT-5.2

Tip: use --model <id>
"""
        models = parse_cursor_list_models(stdout)
        ids = [m["id"] for m in models]
        self.assertEqual(ids[0], CODING_AGENT_MODEL_AUTO)
        self.assertIn("composer-2.5", ids)
        self.assertIn("gpt-5.2", ids)
        self.assertNotIn("auto", ids[1:])

    def test_build_smoke_argv_agent_auto(self) -> None:
        argv = build_smoke_argv("agent", CODING_AGENT_MODEL_AUTO)
        self.assertEqual(argv[0], "agent")
        self.assertIn("-p", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("--trust", argv)
        self.assertNotIn("--model", argv)

    def test_build_smoke_argv_agent_plain_fallback(self) -> None:
        argv = build_smoke_argv("agent", CODING_AGENT_MODEL_AUTO, json_output=False)
        self.assertIn("--trust", argv)
        self.assertNotIn("--output-format", argv)

    def test_build_smoke_argv_agent_explicit_model(self) -> None:
        argv = build_smoke_argv("agent", "composer-2.5")
        self.assertIn("--model", argv)
        self.assertIn("composer-2.5", argv)

    def test_agent_plain_smoke_interpretation(self) -> None:
        self.assertTrue(
            _interpret_smoke_result(
                "agent",
                returncode=0,
                stdout="Hello! How can I help you today?",
                stderr="",
                json_attempt=False,
            )
        )

    def test_agent_smoke_json_unsupported_detection(self) -> None:
        self.assertTrue(
            _agent_smoke_json_unsupported("", "error: unknown option --output-format")
        )

    def test_build_smoke_argv_codex(self) -> None:
        argv = build_smoke_argv("codex", "o4-mini")
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("--json", argv)
        self.assertIn("--model", argv)

    def test_build_smoke_argv_claude_json(self) -> None:
        argv = build_smoke_argv("claude", CODING_AGENT_MODEL_AUTO)
        self.assertIn("--output-format", argv)
        self.assertIn("--dangerously-skip-permissions", argv)

    def test_build_smoke_argv_grok(self) -> None:
        argv = build_smoke_argv("grok", CODING_AGENT_MODEL_AUTO)
        self.assertIn("--prompt", argv)
        self.assertIn("--format", argv)

    def test_build_smoke_argv_gemini(self) -> None:
        argv = build_smoke_argv("gemini", CODING_AGENT_MODEL_AUTO)
        self.assertIn("--yolo", argv)
        self.assertIn("--output-format", argv)

    def test_build_dispatch_argv_codex_sandbox(self) -> None:
        argv = build_dispatch_argv("codex", "do work", CODING_AGENT_MODEL_AUTO)
        self.assertIn("--sandbox", argv)
        self.assertIn("workspace-write", argv)
        self.assertIn("do work", argv)

    def test_build_dispatch_argv_agent_trust(self) -> None:
        argv = build_dispatch_argv("agent", "implement feature", "composer-2.5")
        self.assertIn("--trust", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("composer-2.5", argv)

    def test_smoke_timeout_returns_false(self) -> None:
        def _timeout(cmd, timeout=90):
            raise subprocess.TimeoutExpired(cmd, timeout)

        result = smoke_test_coding_agent("agent", CODING_AGENT_MODEL_AUTO, _timeout)
        self.assertFalse(result)

    def test_workspace_trust_failure_is_auth_fail(self) -> None:
        self.assertFalse(
            _interpret_smoke_result(
                "agent",
                returncode=1,
                stdout="",
                stderr="Workspace Trust Required",
                json_attempt=True,
            )
        )

    def test_home_unbound_is_auth_fail(self) -> None:
        self.assertFalse(
            _interpret_smoke_result(
                "agent",
                returncode=1,
                stdout="",
                stderr="line 18: HOME: unbound variable",
                json_attempt=False,
            )
        )

    def test_authentication_required_is_auth_fail(self) -> None:
        self.assertFalse(
            _interpret_smoke_result(
                "agent",
                returncode=1,
                stdout="",
                stderr="Authentication required",
                json_attempt=True,
            )
        )

    def test_describe_smoke_failure_timeout_mentions_oauth(self) -> None:
        msg = describe_smoke_failure("agent", timed_out=True)
        self.assertIn("timed out", msg.lower())
        self.assertIn("oauth", msg.lower())

    @patch("plugin.coding_agent.binary_on_path", return_value=True)
    @patch("plugin.coding_agent.shutil.which", return_value="/usr/bin/agent")
    def test_agent_probe_runs_before_json_smoke(self, _which, _on_path) -> None:
        calls: list[list[str]] = []

        def _run(cmd, timeout=90):
            calls.append(list(cmd))
            if len(calls) == 1:
                return SimpleNamespace(returncode=0, stdout="ok", stderr="")
            return SimpleNamespace(returncode=0, stdout='{"is_error":false}', stderr="")

        result = smoke_test_coding_agent(
            "agent", CODING_AGENT_MODEL_AUTO, _run, fast=False
        )
        self.assertTrue(result)
        self.assertGreaterEqual(len(calls), 2)
        self.assertNotIn("--output-format", calls[0])
        self.assertIn("--trust", calls[0])
        self.assertIn("--output-format", calls[1])

    @patch("plugin.coding_agent.binary_on_path", return_value=True)
    @patch("plugin.coding_agent.shutil.which", return_value="/usr/bin/agent")
    def test_agent_fast_smoke_single_plain_probe(self, _which, _on_path) -> None:
        calls: list[list[str]] = []

        def _run(cmd, timeout=15):
            calls.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        result = smoke_test_coding_agent(
            "agent", CODING_AGENT_MODEL_AUTO, _run, fast=True
        )
        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--output-format", calls[0])


class TestCodingAgentDiscovery(unittest.TestCase):
    def test_is_contested_agent(self) -> None:
        self.assertTrue(is_contested_binary_name("agent"))
        self.assertFalse(is_contested_binary_name("claude"))
        self.assertFalse(is_contested_binary_name("cursor-agent"))

    def test_resolve_adapter_cursor_agent(self) -> None:
        adapter = resolve_adapter("cursor-agent")
        self.assertEqual(adapter.display_name, "Cursor CLI")
        self.assertEqual(adapter.binary, "agent")

    @patch("plugin.coding_agent.binary_on_path")
    def test_get_available_cursor_agent(self, on_path) -> None:
        on_path.side_effect = lambda name: name == "cursor-agent"
        rows = get_available_coding_binaries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "cursor-agent")
        self.assertIn("Cursor CLI", str(rows[0]["label"]))
        self.assertFalse(rows[0]["contested"])

    @patch("plugin.coding_agent.binary_on_path")
    def test_get_available_contested_agent_only(self, on_path) -> None:
        on_path.side_effect = lambda name: name == "agent"
        rows = get_available_coding_binaries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "agent")
        self.assertTrue(rows[0]["contested"])
        self.assertEqual(rows[0]["label"], CONTESTED_AGENT_LABEL)
        self.assertNotIn("Cursor CLI", str(rows[0]["label"]))


class TestCodingAgentSmokeLive(unittest.TestCase):
    def test_agent_smoke_auto_if_installed(self) -> None:
        from plugin.coding_agent import binary_on_path

        if not binary_on_path("agent"):
            self.skipTest("agent CLI not on PATH")

        def _run(cmd, timeout=90):
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        result = smoke_test_coding_agent("agent", CODING_AGENT_MODEL_AUTO, _run)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
