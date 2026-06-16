"""Tests for verify_goal_cards structured parsing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_goal_cards import count_goal_cards, verify_plan  # noqa: E402


TABLE_FALSE_POSITIVE_PLAN = """---
plan_id: matrix-v5-test
goal_card_budget: 2
goal_rationale: test fixture
---

## Kanban optimization

| Field | Count |
|-------|-------|
| `goal_card: true` | 0 |

### Real goal section

goal_card: true

Acceptance:
- one criterion

```agent
agent -p "do the thing"
```
"""


class TestVerifyGoalCards(unittest.TestCase):
    def test_table_row_does_not_increment_goal_count(self) -> None:
        meta, body = {}, TABLE_FALSE_POSITIVE_PLAN.split("---", 2)[2]
        # Re-parse frontmatter for count_goal_cards
        from verify_goal_cards import _parse_frontmatter

        meta, body = _parse_frontmatter(TABLE_FALSE_POSITIVE_PLAN)
        self.assertEqual(count_goal_cards(meta, body), 1)

    def test_verify_plan_passes_with_table_prose(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".plan.md", delete=False, encoding="utf-8") as f:
            f.write(TABLE_FALSE_POSITIVE_PLAN)
            path = Path(f.name)
        try:
            n_fail, _, failures = verify_plan(path)
            self.assertEqual(n_fail, 0, failures)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
