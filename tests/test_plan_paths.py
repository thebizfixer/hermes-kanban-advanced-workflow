"""Tests for agent-neutral plan path resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from plan_paths import (  # noqa: E402
    CANONICAL_PLAN_DIR,
    DEFAULT_PLAN_SEARCH_DIRS,
    ensure_canonical_plan,
    is_governance_artifact_path,
    load_plan_search_dirs,
    resolve_plan_file,
)


class TestPlanPaths(unittest.TestCase):
    def test_default_search_dirs_include_hermes_and_agent(self) -> None:
        self.assertIn(".hermes/kanban/plans", DEFAULT_PLAN_SEARCH_DIRS)
        self.assertIn(".agent/plans", DEFAULT_PLAN_SEARCH_DIRS)

    def test_resolve_from_agent_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".agent" / "plans"
            plan_dir.mkdir(parents=True)
            plan_path = plan_dir / "matrix-v5.plan.md"
            plan_path.write_text("# plan\n", encoding="utf-8")
            found = resolve_plan_file(root, "matrix-v5")
            self.assertEqual(found, plan_path.resolve())

    def test_resolve_hint_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hint = root / "custom" / "my.plan.md"
            hint.parent.mkdir(parents=True)
            hint.write_text("# plan\n", encoding="utf-8")
            found = resolve_plan_file(root, "other-id", str(hint))
            self.assertEqual(found, hint.resolve())

    def test_resolve_prefers_canonical_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = root / ".agent" / "plans"
            agent_dir.mkdir(parents=True)
            agent_path = agent_dir / "matrix-v5.plan.md"
            agent_path.write_text("# draft\n", encoding="utf-8")

            canonical_dir = root / CANONICAL_PLAN_DIR
            canonical_dir.mkdir(parents=True)
            canonical_path = canonical_dir / "matrix-v5.plan.md"
            canonical_path.write_text("# canonical\n", encoding="utf-8")

            found = resolve_plan_file(root, "matrix-v5")
            self.assertEqual(found, canonical_path.resolve())

    def test_ensure_canonical_plan_copies_from_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft_dir = root / ".cursor" / "plans"
            draft_dir.mkdir(parents=True)
            draft_path = draft_dir / "my-feature.plan.md"
            draft_path.write_text("# draft plan\n", encoding="utf-8")

            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "plan_search_dirs:\n  - .cursor/plans\n",
                encoding="utf-8",
            )

            result = ensure_canonical_plan(root, "my-feature")
            self.assertIsNotNone(result)
            assert result is not None
            expected = (root / CANONICAL_PLAN_DIR / "my-feature.plan.md").resolve()
            self.assertEqual(result, expected)
            self.assertEqual(result.read_text(encoding="utf-8"), "# draft plan\n")

    def test_ensure_canonical_plan_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical_dir = root / CANONICAL_PLAN_DIR
            canonical_dir.mkdir(parents=True)
            canonical_path = canonical_dir / "p1.plan.md"
            canonical_path.write_text("# already canonical\n", encoding="utf-8")

            result = ensure_canonical_plan(root, "p1")
            self.assertEqual(result, canonical_path.resolve())
            self.assertEqual(result.read_text(encoding="utf-8"), "# already canonical\n")

    def test_is_governance_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(is_governance_artifact_path(".hermes/kanban/plans/foo.plan.md", root))
            self.assertTrue(is_governance_artifact_path(".agent/plans/foo.plan.md", root))
            self.assertTrue(is_governance_artifact_path("docs/reference/foo.md", root))
            self.assertFalse(is_governance_artifact_path("src/app/main.py", root))

    def test_load_plan_search_dirs_from_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "plan_search_dirs:\n  - custom/plans\n",
                encoding="utf-8",
            )
            dirs = load_plan_search_dirs(root)
            self.assertIn("custom/plans", dirs)


if __name__ == "__main__":
    unittest.main()
