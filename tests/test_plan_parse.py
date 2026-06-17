"""Tests for scripts/lib/plan_parse.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import plan_parse as pp  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "plans"


class TestPlanParse(unittest.TestCase):
    def test_matrix_v5_seven_cards(self) -> None:
        plan = FIXTURES / "matrix_v5_sample.plan.md"
        parsed = pp.parse_plan(str(plan))
        self.assertEqual(parsed["plan_id"], "matrix-v5-fixture")
        self.assertEqual(len(parsed["cards"]), 7)

    def test_card_ordinals_sequential(self) -> None:
        text = (FIXTURES / "matrix_v5_sample.plan.md").read_text(encoding="utf-8")
        section = pp.extract_optimization_section(text)
        ordinals = pp.list_card_ordinals(section)
        self.assertEqual(ordinals, list(range(1, 8)))
        self.assertIsNone(pp.validate_card_ordinals(ordinals))

    def test_card_ordinals_gap(self) -> None:
        text = (FIXTURES / "optimization_ordinals_gap.plan.md").read_text(encoding="utf-8")
        section = pp.extract_optimization_section(text)
        ordinals = pp.list_card_ordinals(section)
        err = pp.validate_card_ordinals(ordinals)
        self.assertIsNotNone(err)
        self.assertIn("Card 2", err)

    def test_extract_anchors(self) -> None:
        text = (FIXTURES / "anchors_sample.plan.md").read_text(encoding="utf-8")
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/foo.py")
        self.assertEqual(anchors[0].line, 10)

    def test_extract_anchors_files_plural_bold(self) -> None:
        text = """**Files:** backend/app/services/bar.py

Anchor: `load` at L42
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/bar.py")
        self.assertEqual(anchors[0].line, 42)

    def test_extract_anchors_yaml_files_list(self) -> None:
        text = """#### Card 2 — example
files:
  - backend/app/services/tinyfish_sample_quality.py

```agent
Anchor: helper at L100
```
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/tinyfish_sample_quality.py")
        self.assertEqual(anchors[0].line, 100)

    def test_extract_anchors_plain_files_in_agent_block(self) -> None:
        text = """```agent
Files: backend/app/services/baz.py (modify-only)
Anchor: class Baz L55
```
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/baz.py")
        self.assertEqual(anchors[0].line, 55)

    def test_workstream_conflict_flag(self) -> None:
        text = (FIXTURES / "matrix_v5_sample.plan.md").read_text(encoding="utf-8")
        self.assertEqual(pp.workstream_file_conflict_flag(text), 0)


if __name__ == "__main__":
    unittest.main()
