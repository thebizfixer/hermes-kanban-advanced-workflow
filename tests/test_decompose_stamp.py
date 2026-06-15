"""Tests for decompose_stamp.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import decompose_stamp as ds  # noqa: E402


class TestDecomposeStamp(unittest.TestCase):
    def test_stamp_parent_branches_and_call_sites(self) -> None:
        card = {
            "key": "card2",
            "type": "code-gen",
            "wave_parent": "card1",
            "agent_body": (
                'agent -p "task"\n'
                "Call-sites: app/foo.py:bar\n"
                "Acceptance:\n"
                "- Done when: tests pass\n"
            ),
            "body": "plan_id: p1\nfiles:\n  - a.py\n---\n```agent\n...\n```",
        }
        ds.stamp_impl_card(card, plan_id="p1", plan_file_rel=".agent/plans/p1.plan.md")
        self.assertIn("Parent-branches: kanban/p1/card1", card["body"])
        self.assertIn("Call-sites: app/foo.py:bar", card["body"])
        self.assertIn("Acceptance:", card["body"])

    def test_normalize_parent_key(self) -> None:
        self.assertEqual(ds.normalize_parent_key("Card 3"), "card3")


if __name__ == "__main__":
    unittest.main()
