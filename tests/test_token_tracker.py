"""Tests for orchestrator token_tracker logging."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import token_tracker as tt  # noqa: E402


class TestTokenTracker(unittest.TestCase):
    def test_log_orchestrator_tokens_writes_hermes_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "tokens.jsonl"
            original = tt._token_log_path
            tt._token_log_path = lambda: log_path  # type: ignore[method-assign, assignment]
            try:
                path = tt.log_orchestrator_tokens(
                    plan_id="p1",
                    checkpoint="planning-complete",
                    turns=5,
                    note="test",
                )
                self.assertEqual(path, str(log_path))
                row = json.loads(log_path.read_text(encoding="utf-8").strip())
                self.assertEqual(row["plan_id"], "p1")
                self.assertEqual(row["source"], "orchestrator")
                self.assertEqual(row["hermes"]["turns"], 5)
                self.assertEqual(row["hermes"]["total"], 15000)
            finally:
                tt._token_log_path = original  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
