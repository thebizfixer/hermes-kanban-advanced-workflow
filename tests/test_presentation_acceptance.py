"""Tests for presentation_acceptance.py evaluation logic."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from presentation_acceptance import run_presentation_checks  # noqa: E402


class TestPresentationAcceptance(unittest.TestCase):
    def test_line_order_only_skips_entry_transition(self) -> None:
        """Line-order acceptance must not require motion pattern in route shell."""
        with tempfile.TemporaryDirectory() as tmp:
            frontend = Path(tmp) / "frontend" / "app"
            frontend.mkdir(parents=True)
            shell = frontend / "page.tsx"
            shell.write_text(
                "<Loader />\n<div>other</div>\n<Panel />\n",
                encoding="utf-8",
            )
            body = """
Acceptance (layout):
- line number of `Loader` < line number of `Panel`
"""
            ok, err = run_presentation_checks(body, tmp)
            self.assertTrue(ok, err)

    def test_motion_bullet_requires_transition_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frontend = Path(tmp) / "frontend" / "app"
            frontend.mkdir(parents=True)
            shell = frontend / "page.tsx"
            shell.write_text("<Loader />\n<Panel />\n", encoding="utf-8")
            body = """
Acceptance (layout):
- Done when: detail wrapper matches fade-in transition pattern
"""
            ok, err = run_presentation_checks(body, tmp)
            self.assertFalse(ok)
            self.assertEqual(err, "E028")

    def test_empty_body_skips_checks(self) -> None:
        """Mirrors kanban_layout_acceptance.sh SKIP when no card body."""
        ok, err = run_presentation_checks("", tempfile.gettempdir())
        self.assertTrue(ok)
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
