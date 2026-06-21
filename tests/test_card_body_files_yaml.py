"""Tests for card_body Files: vs YAML files: clobber guard (Issue 4 / Card 1)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from card_body import parse_card_body  # noqa: E402


class TestCardBodyFilesYaml(unittest.TestCase):
    def test_yaml_files_first_followed_by_files_ignored(self) -> None:
        """YAML files: populated → trailing Files: line must be ignored."""
        body = """Type: code
files:
- scripts/lib/card_body.py
- tests/test_card_body_layout.py
Mode: modify-only
Tests: pytest -q
Commit: fix: example
Files: docs/x.md (modify-only)
"""
        parsed = parse_card_body(body)
        self.assertEqual(
            parsed["files"],
            ["scripts/lib/card_body.py", "tests/test_card_body_layout.py"],
        )

    def test_files_line_only_still_works(self) -> None:
        """Inline Files: without YAML files: must still work."""
        body = """Type: code
Files: scripts/lib/card_body.py, tests/test_card_body_layout.py
Mode: modify-only
Tests: pytest -q
Commit: fix: example
"""
        parsed = parse_card_body(body)
        self.assertEqual(
            parsed["files"],
            ["scripts/lib/card_body.py", "tests/test_card_body_layout.py"],
        )

    def test_files_first_wins_over_yaml(self) -> None:
        """Files: parsed first → YAML files: must not overwrite."""
        body = """Type: code
Files: scripts/lib/card_body.py
Mode: modify-only
files:
- scripts/should_not_appear.py
Tests: pytest -q
Commit: fix: example
"""
        parsed = parse_card_body(body)
        self.assertEqual(parsed["files"], ["scripts/lib/card_body.py"])

    def test_yaml_files_list_preserved(self) -> None:
        """YAML files: with multiple entries must be preserved (no Files: line)."""
        body = """Type: code
files:
- scripts/lib/card_body.py
- scripts/lib/card_body_fidelity.py
- scripts/verify_optimization.sh
Mode: modify-only
Tests: pytest -q
Commit: fix: example
"""
        parsed = parse_card_body(body)
        self.assertEqual(
            parsed["files"],
            [
                "scripts/lib/card_body.py",
                "scripts/lib/card_body_fidelity.py",
                "scripts/verify_optimization.sh",
            ],
        )


if __name__ == "__main__":
    unittest.main()
