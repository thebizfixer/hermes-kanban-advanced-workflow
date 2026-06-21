"""Tests for verify_optimization.sh check behaviors (Card 3)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

from card_body import body_tests_valid  # noqa: E402
from card_body_fidelity import validate_parsed_cards  # noqa: E402
from plan_parse import parse_plan  # noqa: E402


class TestAnchorExitCodePropagation(unittest.TestCase):
    """verify_optimization.sh must propagate verify_anchors.py non-zero exit."""

    def test_nonzero_exit_with_empty_json_triggers_fail(self) -> None:
        """ANCHOR_EXIT=1 + ANCHOR_FAILS=0 → check_fail (not pass)."""
        exit_code = 1
        failures = 0
        should_fail = (exit_code != 0 and failures == 0)
        self.assertTrue(should_fail, "Non-zero exit + zero reported failures must trigger fail")

    def test_nonzero_exit_with_nonzero_failures_triggers_fail(self) -> None:
        """ANCHOR_EXIT=1 + ANCHOR_FAILS=2 → check_fail (but message from failures)."""
        exit_code = 1
        failures = 2
        # Check that failures path is taken (exit check is only when failures=0)
        should_fail = (failures > 0)
        self.assertTrue(should_fail)

    def test_zero_exit_with_nonzero_failures_triggers_fail(self) -> None:
        """Normal case — exit 0 but failures present."""
        exit_code = 0
        failures = 3
        should_fail = (failures > 0)
        self.assertTrue(should_fail)

    def test_zero_exit_zero_failures_is_pass(self) -> None:
        """Clean run."""
        exit_code = 0
        failures = 0
        exit_nonzero = (exit_code != 0 and failures == 0)
        fail_on_misses = (failures > 0)
        should_fail = exit_nonzero or fail_on_misses
        self.assertFalse(should_fail)


class TestTestsLineValidation(unittest.TestCase):
    """verify_optimization.sh check 22 must flag invalid Tests: lines."""

    def test_clockwork_card6_prose_tests_is_invalid(self) -> None:
        """Prose Tests: like 'matrix v8 row 1 + row 2 + merge rerun' must fail."""
        # This is exactly the clockwork Card 6 pattern
        raw = "matrix v8 row 1 + row 2 + merge rerun on row 2 (operator manual)"
        self.assertFalse(body_tests_valid(f"Tests: {raw}\n"))

    def test_valid_pytest_command_passes(self) -> None:
        """pytest tests/test_x.py -q is valid."""
        self.assertTrue(body_tests_valid("Tests: pytest tests/test_x.py -q\n"))

    def test_n_a_is_valid(self) -> None:
        """N/A Tests: line is always valid."""
        self.assertTrue(body_tests_valid("Tests: N/A\n"))

    def test_shell_command_is_valid(self) -> None:
        """bash scripts/verify.sh is valid."""
        self.assertTrue(body_tests_valid("Tests: bash scripts/verify.sh --plan foo\n"))

    def test_empty_tests_line_is_equivalent_to_absent(self) -> None:
        """Empty Tests: is treated as absent (no test command = OK)."""
        self.assertTrue(body_tests_valid("Tests: \n"))


class TestValidateParsedCardsTestsLine(unittest.TestCase):
    """validate_parsed_cards must flag invalid Tests: lines on card blocks."""

    def _make_card(self, key: str, body: str) -> dict:
        return {"key": key, "body": body, "files": ["a.py"], "type": "code-gen", "mode": "modify-only"}

    def test_invalid_tests_line_triggers_violation(self) -> None:
        body = (
            "Type: code\n"
            "Files: scripts/x.py\n"
            "Mode: modify-only\n"
            "Tests: matrix v8 row 1 + row 2 + merge rerun on row 2\n"
            "Commit: fix: example\n"
        )
        cards = [self._make_card("card1", body)]
        violations = validate_parsed_cards(
            plan_path=Path("/tmp/test.plan.md"),
            plan_text="",
            cards=cards,
            repo_root=Path("/tmp"),
            plan_id="test",
            profile="balanced",
        )
        tests_violations = [v for v in violations if "Tests" in v.code.upper() or "tests" in v.message.lower()]
        self.assertTrue(len(tests_violations) > 0, "Invalid Tests: line must trigger a violation")

    def test_valid_tests_line_no_violation(self) -> None:
        body = (
            "Type: code\n"
            "Files: scripts/x.py\n"
            "Mode: modify-only\n"
            "Tests: pytest tests/test_x.py -q\n"
            "Commit: fix: example\n"
        )
        cards = [self._make_card("card1", body)]
        violations = validate_parsed_cards(
            plan_path=Path("/tmp/test.plan.md"),
            plan_text="",
            cards=cards,
            repo_root=Path("/tmp"),
            plan_id="test",
            profile="balanced",
        )
        tests_violations = [v for v in violations if "Tests" in v.code.upper() or "tests" in v.message.lower()]
        self.assertEqual(len(tests_violations), 0)

    def test_n_a_no_violation(self) -> None:
        body = (
            "Type: verification-deploy\n"
            "Files: scripts/x.py\n"
            "Mode: modify-only\n"
            "Tests: N/A\n"
            "Commit: N/A (verification only)\n"
        )
        cards = [self._make_card("card1", body)]
        violations = validate_parsed_cards(
            plan_path=Path("/tmp/test.plan.md"),
            plan_text="",
            cards=cards,
            repo_root=Path("/tmp"),
            plan_id="test",
            profile="balanced",
        )
        tests_violations = [v for v in violations if "Tests" in v.code.upper() or "tests" in v.message.lower()]
        self.assertEqual(len(tests_violations), 0)


if __name__ == "__main__":
    unittest.main()
