"""Tests for validate_card_bodies / card_body_fidelity."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from card_body_fidelity import collect_assigned_files, collect_plan_required_files, validate_parsed_cards  # noqa: E402


class TestValidateCardBodies(unittest.TestCase):
    def test_spec_file_must_appear_on_some_card(self) -> None:
        plan_text = """
## Kanban optimization

#### Card 1 — one file
**Files:** scripts/a.py
```agent
Spec:
- touch `scripts/a.py` and `scripts/b.py`
Tests: pytest -q
```
"""
        cards = [
            {
                "key": "card1",
                "type": "code-gen",
                "files": ["scripts/a.py"],
                "tests": "pytest -q",
                "body": "plan_id: p1\n",
            }
        ]
        required = collect_plan_required_files(plan_text, cards)
        self.assertIn("scripts/b.py", required)
        assigned = collect_assigned_files(cards)
        self.assertNotIn("scripts/b.py", assigned)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "a.py").write_text("x", encoding="utf-8")
            violations = validate_parsed_cards(
                plan_path="plan.md",
                plan_text=plan_text,
                cards=cards,
                repo_root=root,
                plan_id="p1",
                profile="balanced",
            )
        codes = {v.code for v in violations}
        self.assertIn("V001_SPEC_FILE_UNASSIGNED", codes)

    def test_advisory_dry_run_style_warn_only_severity(self) -> None:
        plan_text = "## Kanban optimization\n"
        cards = [
            {
                "key": "card1",
                "type": "code-gen",
                "files": ["missing.py"],
                "tests": "pytest",
                "body": "plan_id: p1\n",
                "estimated_lines": 600,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            violations = validate_parsed_cards(
                plan_path="plan.md",
                plan_text=plan_text,
                cards=cards,
                repo_root=Path(tmp),
                plan_id="p1",
                profile="advisory",
            )
        self.assertTrue(all(v.severity == "warn" for v in violations if v.code == "V008_PATH_MISSING"))


if __name__ == "__main__":
    unittest.main()
