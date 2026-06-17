"""Tests for presentation acceptance parsing and verification card taxonomy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from card_body import (  # noqa: E402
    is_verification_deploy,
    is_verification_local,
    is_verification_only,
    parse_card_body,
)
from presentation_acceptance import (  # noqa: E402
    parse_presentation_acceptance,
    parse_surface_slots,
)


class TestPresentationAcceptanceParse(unittest.TestCase):
    def test_parse_layout_line_order(self) -> None:
        body = """
Acceptance (layout):
- line number of `PrimaryLoader` < line number of `StatusPanel`
"""
        parsed = parse_presentation_acceptance(body)
        self.assertEqual(len(parsed["layout"]), 1)
        self.assertEqual(parsed["layout"][0]["kind"], "line_order")

    def test_parse_a11y_reduced_motion(self) -> None:
        body = """
Acceptance (a11y):
- reduced-motion path disables slide via prefers-reduced-motion
"""
        parsed = parse_presentation_acceptance(body)
        self.assertTrue(any(r["kind"] == "reduced_motion" for r in parsed["a11y"]))

    def test_surface_slots(self) -> None:
        text = """
Surface-slots:
  primary_loader_slot: loader region
  status_panel: pending panel wrapper
"""
        slots = parse_surface_slots(text)
        self.assertEqual(slots, ["primary_loader_slot", "status_panel"])

    def test_card_body_includes_presentation_acceptance(self) -> None:
        body = """Type: code-gen
Files: frontend/app/page.tsx
Acceptance (layout):
- line number of `Loader` < line number of `Panel`
"""
        parsed = parse_card_body(body)
        self.assertIn("presentation_acceptance", parsed)
        self.assertTrue(parsed["presentation_acceptance"]["layout"])


class TestVerificationTaxonomy(unittest.TestCase):
    def test_verification_local_legacy_type(self) -> None:
        body = """Type: verification
Tests: pytest tests/test_x.py
Commit: N/A (verification only)
Mode: read-only
"""
        parsed = parse_card_body(body)
        self.assertTrue(is_verification_local(parsed, body))
        self.assertFalse(is_verification_deploy(parsed, body))

    def test_verification_deploy_requires_deploy_or_type(self) -> None:
        body = """Type: verification-deploy
Tests: bash scripts/smoke.sh
Deploy: docker compose up -d
Mode: read-only
"""
        parsed = parse_card_body(body)
        self.assertTrue(is_verification_deploy(parsed, body))

    def test_verification_deploy_deploy_line_without_type(self) -> None:
        body = """Type: verification-local
Deploy: operator browser smoke
Tests: echo ok
"""
        parsed = parse_card_body(body)
        self.assertTrue(is_verification_deploy(parsed, body))
        self.assertFalse(is_verification_only(parsed, body))


if __name__ == "__main__":
    unittest.main()
