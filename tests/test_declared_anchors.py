"""Tests for declared-anchor audit and parsing."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import plan_parse as pp  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "plans"


class TestDeclaredAnchors(unittest.TestCase):
    def test_colocated_anchor(self) -> None:
        text = (FIXTURES / "anchors_sample.plan.md").read_text(encoding="utf-8")
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/foo.py")
        self.assertEqual(anchors[0].line, 10)

    def test_canonical_anchor_in_agent_block(self) -> None:
        text = """## Kanban optimization

#### Card 1 — example
files:
  - backend/app/services/bar.py

```agent
Files: backend/app/services/bar.py (modify-only)
Anchor: backend/app/services/bar.py::load@L42
```
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/bar.py")
        self.assertEqual(anchors[0].line, 42)
        self.assertEqual(anchors[0].symbol_hint, "load")

    def test_relaxed_anchor_uses_card_files(self) -> None:
        text = """## Kanban optimization

#### Card 2 — example
files:
  - backend/app/services/baz.py

```agent
Files: backend/app/services/baz.py (modify-only)
Anchor: `Baz` at L55
```
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].file, "backend/app/services/baz.py")
        self.assertEqual(anchors[0].line, 55)

    def test_contracts_block(self) -> None:
        text = """## Kanban optimization

Contracts:
- backend/app/services/shared.py::helper@L100

#### Card 1 — x
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].line, 100)

    def test_prose_only_line_ref_not_extracted(self) -> None:
        text = """## Kanban optimization

Signal: example.py L1864 does something.

#### Card 1 — example
files:
  - backend/app/services/example.py

```agent
Fix the handler.
```
"""
        anchors = pp.extract_anchors(text)
        self.assertEqual(anchors, [])

    def test_audit_flags_missing_anchor(self) -> None:
        text = """## Kanban optimization

#### Card 1 — example
files:
  - backend/a.py
  - backend/b.py

```agent
Files: backend/a.py, backend/b.py
Call-sites: backend/c.py:handler
Spec:
- Behavior: change handler
```
"""
        report = pp.audit_anchors(text)
        self.assertIn("card1", report["cards_missing_anchor"])

    def test_audit_ignores_trivial_card(self) -> None:
        text = """## Kanban optimization

#### Card 1 — trivial
files:
  - backend/a.py

```agent
Files: backend/a.py
Rename constant FOO.
```
"""
        report = pp.audit_anchors(text)
        self.assertEqual(report["cards_missing_anchor"], [])

    def test_markdown_link_files_flagged(self) -> None:
        text = """## Kanban optimization

#### Card 1 — example
files:
  - backend/a.py

```agent
Files: [`backend/a.py`](../backend/a.py) (modify-only)
Anchor: backend/a.py::foo@L1
```
"""
        report = pp.audit_anchors(text)
        self.assertEqual(len(report["files_not_plain_path"]), 1)

    def test_audit_finds_anchor_after_agent_preamble(self) -> None:
        text = """## Kanban optimization

#### Card 1 — example
files:
  - backend/a.py

```agent
agent -p "Implement the change"
Files: backend/a.py (modify-only)
Call-sites: backend/a.py:handler
Spec:
- Behavior: change handler
Anchor: backend/a.py::handler@L10
```
"""
        report = pp.audit_anchors(text)
        self.assertEqual(report["cards_missing_anchor"], [])

    def test_parse_card_investigate_title_is_code_gen(self) -> None:
        block = """#### Card 6 — Merge overyield: investigate + clamp
files:
  - backend/a.py

```agent
Files: backend/a.py
Anchor: backend/a.py::foo@L1
```
"""
        card = pp.parse_card_block(block)
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card["type"], "code-gen")

    def test_parse_card_quality_gate_title_is_gate(self) -> None:
        block = """#### Card 4 — Matrix quality gate
Type: gate
"""
        card = pp.parse_card_block(block)
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card["type"], "gate")

    def test_parse_anchor_body_canonical(self) -> None:
        parsed = pp.parse_anchor_body("backend/app/x.py::run@L99")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed[0], "backend/app/x.py")
        self.assertEqual(parsed[1], 99)
        self.assertEqual(parsed[2], "run")


if __name__ == "__main__":
    unittest.main()
