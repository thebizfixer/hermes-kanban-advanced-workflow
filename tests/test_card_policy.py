"""Tests for card body policy with decompose-style YAML frontmatter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from kanban_card_policy import load_policy, validate_card  # noqa: E402


class TestCardPolicy(unittest.TestCase):
    def test_decompose_style_body_passes_p001_p003(self) -> None:
        body = """plan_id: plan-x
files:
  - src/foo.py
mode: modify-only
tests: pytest tests/test_foo.py
commit: "feat: add foo"
```agent
do work
```
"""
        policy = load_policy("/nonexistent")
        violations = validate_card("t_test", body, policy)
        codes = [v.get("error_code", "") for v in violations]
        self.assertNotIn("P001_MISSING_FILES_LINE", codes)
        self.assertNotIn("P003", str(codes))

    def test_verification_carve_out(self) -> None:
        body = """Type: verification
Tests: pytest tests/test_x.py
Commit: N/A (verification only)
Mode: read-only
"""
        policy = load_policy("/nonexistent")
        violations = validate_card("t_test", body, policy)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
