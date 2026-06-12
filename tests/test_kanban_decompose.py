"""Tests for kanban_decompose.py plan parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kanban_decompose as decompose  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "plans"


class TestKanbanDecompose(unittest.TestCase):
    def test_matrix_v5_fixture_seven_cards(self) -> None:
        plan = FIXTURES / "matrix_v5_sample.plan.md"
        parsed = decompose.parse_plan(str(plan))
        self.assertEqual(parsed["plan_id"], "matrix-v5-fixture")
        self.assertEqual(len(parsed["cards"]), 7)
        titles = [c["title"] for c in parsed["cards"]]
        self.assertTrue(any("Card 7" in t for t in titles))
        self.assertEqual(parsed["cards"][0]["files"][0], "backend/app/config.py")
        self.assertEqual(parsed["cards"][-1]["type"], "verification")

    def test_markdown_files_parsing(self) -> None:
        plan = FIXTURES / "markdown_files.plan.md"
        parsed = decompose.parse_plan(str(plan))
        self.assertEqual(len(parsed["cards"]), 1)
        self.assertEqual(parsed["cards"][0]["files"], ["src/a.py", "src/b.py"])
        self.assertEqual(parsed["cards"][0]["mode"], "modify-only")

    def test_split_card_blocks_includes_eof_card(self) -> None:
        content = (FIXTURES / "matrix_v5_sample.plan.md").read_text(encoding="utf-8")
        section = decompose._extract_optimization_section(content)
        blocks = decompose._split_card_blocks(section)
        self.assertEqual(len(blocks), 7)
        self.assertIn("#### Card 7", blocks[-1])

    def test_gate_card_gets_pre_existing_in_body(self) -> None:
        block = """#### Card 1 — Gate

**Type:** gate

```agent
plan_id: test
Run gate.
```
"""
        card = decompose.parse_card_block(block)
        assert card is not None
        self.assertEqual(card["type"], "gate")
        self.assertIn("pre_existing: true", card["body"])


if __name__ == "__main__":
    unittest.main()
