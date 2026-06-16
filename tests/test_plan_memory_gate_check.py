"""Tests for plan memory gate check."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import plan_memory_gate_check as gate  # noqa: E402


class TestPlanMemoryGateCheck(unittest.TestCase):
    def test_card_count_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.plan.md"
            plan.write_text(
                (ROOT / "tests/fixtures/plans/matrix_v5_sample.plan.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            mem = root / "mem.json"
            mem.write_text(json.dumps({"card_count": 99, "plan_path": str(plan)}), encoding="utf-8")
            rc = gate.main(
                [
                    "--memory",
                    str(mem),
                    "--plan",
                    str(plan),
                    "--repo-root",
                    str(root),
                    "--bundle-scripts",
                    str(ROOT / "scripts"),
                ]
            )
            self.assertEqual(rc, 1)

    def test_matching_card_count_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.plan.md"
            plan.write_text(
                (ROOT / "tests/fixtures/plans/matrix_v5_sample.plan.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            impl = gate._impl_card_count(plan, ROOT / "scripts")
            mem = root / "mem.json"
            mem.write_text(
                json.dumps({"card_count": impl, "plan_path": str(plan)}),
                encoding="utf-8",
            )
            rc = gate.main(
                [
                    "--memory",
                    str(mem),
                    "--plan",
                    str(plan),
                    "--repo-root",
                    str(root),
                    "--bundle-scripts",
                    str(ROOT / "scripts"),
                ]
            )
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
