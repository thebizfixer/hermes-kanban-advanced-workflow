"""Tests for Tests: line sanitize and P014 validation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

from card_body import (  # noqa: E402
    body_tests_valid,
    normalize_file_path,
    parse_card_body,
    sanitize_tests_command,
    validate_tests_command_syntax,
)
import kanban_card_policy as policy  # noqa: E402


class TestSanitizeTestsCommand(unittest.TestCase):
    def test_strips_trailing_parenthetical(self) -> None:
        raw = "python -m pytest tests/test_foo.py (verify output)"
        self.assertEqual(sanitize_tests_command(raw), "python -m pytest tests/test_foo.py")

    def test_preserves_na(self) -> None:
        self.assertEqual(sanitize_tests_command("N/A"), "N/A")

    def test_parse_card_body_applies_sanitize(self) -> None:
        body = "Tests: pytest tests/x.py (smoke)\n"
        parsed = parse_card_body(body)
        self.assertEqual(parsed["tests"], "pytest tests/x.py")


class TestValidateTestsCommandSyntax(unittest.TestCase):
    def test_valid_pytest(self) -> None:
        ok, err = validate_tests_command_syntax("pytest -q tests/test_a.py")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_unbalanced_parens_denied(self) -> None:
        ok, err = validate_tests_command_syntax("pytest tests/(bad.py")
        self.assertFalse(ok)
        self.assertIn("parentheses", (err or "").lower())

    def test_parenthetical_only_fixed_by_sanitize(self) -> None:
        raw = "pytest tests/x.py (note)"
        ok, _ = validate_tests_command_syntax(raw)
        self.assertTrue(ok)

    def test_body_tests_valid_rejects_bad_shell(self) -> None:
        body = "Tests: echo 'unclosed\nMode: modify-only\n"
        self.assertFalse(body_tests_valid(body))


class TestNormalizeFilePath(unittest.TestCase):
    def test_strips_mode_suffix(self) -> None:
        self.assertEqual(
            normalize_file_path("scripts/foo.py (modify-only)"),
            "scripts/foo.py",
        )

    def test_parse_card_body_normalizes_files(self) -> None:
        body = "Files: a.py (read-only), b.py (modify-only)\n"
        parsed = parse_card_body(body)
        self.assertEqual(parsed["files"], ["a.py", "b.py"])


class TestP014Policy(unittest.TestCase):
    def test_p014_blocks_malformed_tests(self) -> None:
        body = (
            "plan_id: p1\n"
            "Files: a.py\n"
            "Tests: pytest tests/(bad.py\n"
            "Mode: modify-only\n"
            "```agent\nagent -p 'x'\n```"
        )
        rules = [
            {
                "condition": "Tests: line is malformed (shlex or parentheses)",
                "error_code": "P014",
            }
        ]
        violations = policy.validate_card("t_x", body, {"rules": rules})
        self.assertEqual(len(violations), 1)

    def test_p014_skips_verification_card(self) -> None:
        body = (
            "Type: verification\n"
            "Tests: pytest tests/(bad.py\n"
            "Commit: N/A (verification only)\n"
        )
        violations = policy.validate_card("t_x", body, {"rules": []})
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
