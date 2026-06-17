"""Recovery map includes presentation acceptance error codes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kanban_recover  # noqa: E402


class TestKanbanRecoverPresentation(unittest.TestCase):
    def test_recovery_map_includes_e028_e029(self) -> None:
        self.assertIn("E028_LAYOUT_ACCEPTANCE_FAILED", kanban_recover.RECOVERY_MAP)
        self.assertIn("E029_PRESENTATION_A11Y_FAILED", kanban_recover.RECOVERY_MAP)


if __name__ == "__main__":
    unittest.main()
