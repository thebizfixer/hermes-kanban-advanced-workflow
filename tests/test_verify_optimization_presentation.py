"""Tests for verify_optimization presentation checks 19–21 (Python SSOT)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from verify_optimization_presentation import (  # noqa: E402
    count_motion_without_a11y,
    count_presentation_acceptance_gaps,
    load_plan_text,
    missing_ui_stack_or_surface_slots,
)

FIXTURES = ROOT / "tests" / "fixtures" / "plans"


class TestVerifyOptimizationPresentation(unittest.TestCase):
    def test_good_fixture_passes_checks(self) -> None:
        text = load_plan_text(FIXTURES / "presentation_opt_good.plan.md")
        self.assertEqual(count_presentation_acceptance_gaps(text), 0)
        self.assertEqual(missing_ui_stack_or_surface_slots(text), 0)
        self.assertEqual(count_motion_without_a11y(text), 0)

    def test_bad_layout_fixture_fails_check_19(self) -> None:
        text = load_plan_text(FIXTURES / "presentation_opt_bad_layout.plan.md")
        self.assertGreater(count_presentation_acceptance_gaps(text), 0)

    def test_bad_layout_has_surface_slots_for_check_20(self) -> None:
        text = load_plan_text(FIXTURES / "presentation_opt_bad_layout.plan.md")
        self.assertEqual(missing_ui_stack_or_surface_slots(text), 0)

    def test_motion_without_a11y_in_bad_fixture(self) -> None:
        text = load_plan_text(FIXTURES / "presentation_opt_bad_layout.plan.md")
        self.assertGreater(count_motion_without_a11y(text), 0)


if __name__ == "__main__":
    unittest.main()
