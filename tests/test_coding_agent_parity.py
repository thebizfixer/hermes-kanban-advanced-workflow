"""Parity audit: coding_agent_invoke.sh vs plugin/coding_agent.py adapters."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVOKE = REPO / "scripts" / "coding_agent_invoke.sh"
ADAPTERS = REPO / "plugin" / "coding_agent.py"

# (label, token required in invoke.sh, token required in coding_agent.py)
PARITY_ROWS = (
    ("cursor trust", "--trust", "--trust"),
    ("claude permissions", "--dangerously-skip-permissions", "--dangerously-skip-permissions"),
    ("codex json", "--json", "--json"),
    ("codex sandbox dispatch", "workspace-write", "workspace-write"),
    ("gemini yolo", "--yolo", "--yolo"),
    ("grok always-approve", "--always-approve", "--always-approve"),
    ("aider yes-always", "--yes-always", "--yes-always"),
    ("hermes yolo", "--yolo", "--yolo"),
)


class TestCodingAgentParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.invoke_text = INVOKE.read_text(encoding="utf-8")
        cls.adapter_text = ADAPTERS.read_text(encoding="utf-8")

    def test_invoke_and_adapters_share_headless_flags(self) -> None:
        for label, invoke_token, adapter_token in PARITY_ROWS:
            with self.subTest(label=label):
                self.assertIn(
                    invoke_token,
                    self.invoke_text,
                    f"{INVOKE.name} missing {invoke_token}",
                )
                self.assertIn(
                    adapter_token,
                    self.adapter_text,
                    f"{ADAPTERS.name} missing {adapter_token}",
                )


if __name__ == "__main__":
    unittest.main()
