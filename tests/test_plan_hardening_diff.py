"""Tests for plan_hardening_diff.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

from plan_hardening_diff import run_diff  # noqa: E402


class TestPlanHardeningDiff(unittest.TestCase):
    def test_verify_pattern_miss(self) -> None:
        plan = """---
plan_id: p1
---
## Kanban optimization
Acceptance:
- Verify: rg -n "quality_gate FAIL" scripts/module_a.py
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "module_a.py").write_text("# no match\n", encoding="utf-8")
            plan_path = root / "plan.md"
            plan_path.write_text(plan, encoding="utf-8")
            drift = run_diff(plan_path, root)
        kinds = {d.kind for d in drift}
        self.assertIn("verify_pattern_miss", kinds)


if __name__ == "__main__":
    unittest.main()
