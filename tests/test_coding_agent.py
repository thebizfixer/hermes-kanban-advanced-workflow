"""Unit tests for coding-agent CLI adapters."""

from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace

from plugin.coding_agent import (
    CODING_AGENT_MODEL_AUTO,
    build_smoke_argv,
    is_auto_model,
    normalize_coding_agent_model,
    parse_cursor_list_models,
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
        self.assertIn("--trust", argv)
        self.assertNotIn("--model", argv)

    def test_build_smoke_argv_agent_explicit_model(self) -> None:
        argv = build_smoke_argv("agent", "composer-2.5")
        self.assertIn("--model", argv)
        self.assertIn("composer-2.5", argv)

    def test_build_smoke_argv_codex(self) -> None:
        argv = build_smoke_argv("codex", "o4-mini")
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("--model", argv)


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
