"""Tests for final audit remediation spawn grouping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from final_audit import (  # noqa: E402
    Violation,
    build_remediation_body,
    group_remediation_cards,
)


class TestRemediationSpawn(unittest.TestCase):
    def test_card_body_shape(self) -> None:
        card = {
            "remediates": "t_parent",
            "files": ["docs/a.md"],
            "missed": ["- [tier2] doc_coverage_gap: missing scripts.md"],
            "acceptance": ["Required doc surface updated"],
            "tests": "doc: link-check",
        }
        body = build_remediation_body("my-plan", card)
        self.assertIn("Remediation-phase: final", body)
        self.assertIn("Type: remediation", body)
        self.assertIn("Tests: doc: link-check", body)

    def test_dedupe_same_remediates_and_files(self) -> None:
        v1 = Violation("tier1", "acceptance_miss", "a.py", "a", remediates_task_id="t_1")
        v2 = Violation("tier1", "call_site_miss", "a.py", "b", remediates_task_id="t_1")
        groups = group_remediation_cards([v1, v2])
        self.assertEqual(len(groups), 1)

    def test_skips_warn_severity(self) -> None:
        v = Violation("tier1", "plan_todo_drift", "", "warn only", severity="warn")
        self.assertEqual(group_remediation_cards([v]), [])


if __name__ == "__main__":
    unittest.main()
