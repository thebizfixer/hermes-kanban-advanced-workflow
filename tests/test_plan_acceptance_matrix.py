"""Tests for plan acceptance_matrix extraction and integration-verify warnings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from plan_parse import extract_acceptance_matrix, integration_verify_warnings  # noqa: E402


PLAN_WITH_SLOTS = """---
plan_id: demo-plan
---

## Kanban optimization

Surface-slots:
  loader_slot: region

#### Card 1 — route-wiring

Acceptance (layout):
- line number of `Loader` < line number of `Panel`
"""


class TestAcceptanceMatrix(unittest.TestCase):
    def test_extract_surface_slots_and_cards(self) -> None:
        matrix = extract_acceptance_matrix(PLAN_WITH_SLOTS)
        self.assertIn("loader_slot", matrix["surface_slots"])
        self.assertEqual(len(matrix["presentation_cards"]), 1)

    def test_integration_verify_warning_for_route_cards(self) -> None:
        cards = [{"key": "feature-route-layout", "type": "code-gen"}]
        warnings = integration_verify_warnings(cards, PLAN_WITH_SLOTS)
        self.assertTrue(any("integration-verify" in w for w in warnings))

    def test_no_warning_when_integration_verify_present(self) -> None:
        cards = [
            {"key": "feature-route-layout", "type": "code-gen"},
            {"key": "integration-verify", "type": "verification-local"},
        ]
        warnings = integration_verify_warnings(cards, PLAN_WITH_SLOTS)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
