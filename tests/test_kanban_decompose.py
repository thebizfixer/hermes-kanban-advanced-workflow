"""Smoke tests for kanban_decompose imports."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kanban_decompose as decompose  # noqa: E402


class TestKanbanDecomposeImports(unittest.TestCase):
    def test_extract_id_uses_re(self) -> None:
        self.assertEqual(decompose.extract_id("Created t_a1b2c3d4 ok"), "t_a1b2c3d4")


if __name__ == "__main__":
    unittest.main()
