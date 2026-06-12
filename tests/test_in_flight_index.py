"""CI guard for in-flight governance index structure."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = (
    REPO_ROOT
    / "plugin"
    / "skills"
    / "kanban-advanced"
    / "references"
    / "in-flight-governance-index.md"
)


class TestInFlightIndex(unittest.TestCase):
    def test_index_exists(self) -> None:
        self.assertTrue(INDEX.is_file(), f"missing {INDEX}")

    def test_layer_sections_present(self) -> None:
        text = INDEX.read_text(encoding="utf-8")
        for marker in (
            "## L0",
            "## L1",
            "## L3",
            "## L4",
            "## L5-pre",
            "## L5 ",
            "## L6",
            "Bundle resolution",
            "kanban_recover.py",
        ):
            self.assertIn(marker, text, f"index missing section: {marker}")

    def test_mirror_pointer(self) -> None:
        mirror = REPO_ROOT / "plugin" / "data" / "references" / "in-flight-governance-index.md"
        self.assertTrue(mirror.is_file())
        self.assertIn("kanban-advanced/references/in-flight-governance-index.md", mirror.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
