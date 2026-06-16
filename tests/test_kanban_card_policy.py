"""Tests for kanban_card_policy P012/P013."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kanban_card_policy as policy  # noqa: E402


class TestCardPolicyCompleteness(unittest.TestCase):
    def test_p012_multi_file_requires_call_sites(self) -> None:
        body = (
            "plan_id: p1\n"
            "Files: a.py, b.py\n"
            "Mode: modify-only\n"
            "```agent\nagent -p 'x'\n```"
        )
        rules = [
            {
                "condition": "code-gen card with 2+ files missing Call-sites:",
                "error_code": "P012",
            }
        ]
        violations = policy.validate_card("t_x", body, {"rules": rules})
        self.assertEqual(len(violations), 1)

    def test_p013_parents_require_parent_branches(self) -> None:
        body = (
            "plan_id: p1\nparents: card1\n"
            "Files: a.py\nMode: modify-only\n"
            "```agent\nagent -p 'x'\nCall-sites: none\nAcceptance:\n- ok\n```"
        )
        rules = [
            {
                "condition": "code-gen card with parents metadata missing Parent-branches:",
                "error_code": "P013",
            }
        ]
        violations = policy.validate_card("t_x", body, {"rules": rules})
        self.assertEqual(len(violations), 1)

    def test_final_remediation_doc_only_skips_p012(self) -> None:
        body = (
            "plan_id: p1\n"
            "Type: remediation\n"
            "Remediation-phase: final\n"
            "Files: wiki/a.md, docs/b.md\n"
            "Mode: modify-only\n"
            "```agent\nagent -p 'x'\nAcceptance:\n- docs updated\n```"
        )
        rules = [
            {
                "condition": "code-gen card with 2+ files missing Call-sites:",
                "error_code": "P012",
            }
        ]
        violations = policy.validate_card("t_x", body, {"rules": rules})
        self.assertEqual(violations, [])

    def test_final_remediation_code_files_still_enforces_p012(self) -> None:
        body = (
            "plan_id: p1\n"
            "Type: remediation\n"
            "Remediation-phase: final\n"
            "Files: a.py, b.py\n"
            "Mode: modify-only\n"
            "```agent\nagent -p 'x'\nAcceptance:\n- fix call sites\n```"
        )
        rules = [
            {
                "condition": "code-gen card with 2+ files missing Call-sites:",
                "error_code": "P012",
            }
        ]
        violations = policy.validate_card("t_x", body, {"rules": rules})
        self.assertEqual(len(violations), 1)


if __name__ == "__main__":
    unittest.main()
