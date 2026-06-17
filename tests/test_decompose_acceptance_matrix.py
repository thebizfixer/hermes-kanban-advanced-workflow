"""decompose_stamp.load_acceptance_matrix falls back to optimization parsing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from decompose_stamp import load_acceptance_matrix  # noqa: E402

PLAN = """---
plan_id: matrix-fallback
---

## Kanban optimization

Surface-slots:
  loader_slot: region

#### Card 1 — route-layout

Acceptance (layout):
- line number of `A` < line number of `B`
"""


class TestDecomposeAcceptanceMatrix(unittest.TestCase):
    def test_extracts_from_optimization_when_no_frontmatter_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(PLAN, encoding="utf-8")
            matrix = load_acceptance_matrix(path)
            self.assertIn("loader_slot", matrix.get("surface_slots", []))
            self.assertTrue(matrix.get("presentation_cards"))


if __name__ == "__main__":
    unittest.main()
