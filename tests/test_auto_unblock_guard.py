"""Tests for auto_unblock remediation guard (shell helper presence)."""

from __future__ import annotations

import unittest
from pathlib import Path


class TestAutoUnblockGuard(unittest.TestCase):
    def test_has_active_remediation_children_helper_defined(self) -> None:
        root = Path(__file__).resolve().parents[1]
        content = (root / "scripts" / "lib" / "auto_unblock_core.sh").read_text(encoding="utf-8")
        self.assertIn("_has_active_remediation_children", content)
        self.assertIn("Type:[[:space:]]*audit", content)
        self.assertIn("Type:[[:space:]]*remediation", content)

    def test_tick_skips_audit_with_active_remediation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        content = (root / "scripts" / "lib" / "auto_unblock_core.sh").read_text(encoding="utf-8")
        self.assertIn("_has_active_remediation_children \"$tid\"", content)
        self.assertIn("kanban list --parent", content)

    def test_validate_board_check13_uses_parent_list(self) -> None:
        root = Path(__file__).resolve().parents[1]
        content = (root / "scripts" / "validate_board.sh").read_text(encoding="utf-8")
        self.assertIn("kanban list --parent \"$tid\"", content)
        self.assertIn("[FAIL check13]", content)


if __name__ == "__main__":
    unittest.main()
