"""Tests for plan_search_dirs defaults in init overlay emission."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.config_overlay import (
    CANONICAL_PLAN_DIR,
    build_overlay_yaml,
    merge_plan_search_dirs_for_emit,
    overlay_path,
)


def _sample_overlay_yaml(
    *,
    existing: dict[str, str] | None = None,
    project_root: Path | None = None,
) -> str:
    return build_overlay_yaml(
        working_branch="main",
        trigger_branch=None,
        coding_agent="agent",
        bundle_path="hermes-kanban-advanced-workflow",
        hermes_home="/home/user/.hermes",
        existing=existing,
        project_root=project_root,
    )


class TestPlanSearchDirsConfig(unittest.TestCase):
    def test_canonical_plan_dir_constant(self) -> None:
        self.assertEqual(CANONICAL_PLAN_DIR, ".hermes/kanban/plans")

    def test_build_overlay_yaml_writes_canonical_plan_search_dirs(self) -> None:
        yaml_text = _sample_overlay_yaml()
        self.assertIn("# Canonical kanban plan directory (SSOT for decomposition)", yaml_text)
        self.assertIn("plan_search_dirs:", yaml_text)
        self.assertIn(f"  - {CANONICAL_PLAN_DIR}", yaml_text)

    def test_reinit_preserves_extra_plan_search_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = overlay_path(root)
            overlay.parent.mkdir(parents=True)
            overlay.write_text(
                "schema_version: \"1.0.0\"\n"
                "working_branch: main\n"
                "plan_search_dirs:\n"
                "  - .cursor/plans\n",
                encoding="utf-8",
            )
            merged = merge_plan_search_dirs_for_emit(overlay)
            self.assertEqual(merged[0], CANONICAL_PLAN_DIR)
            self.assertIn(".cursor/plans", merged)

            yaml_text = _sample_overlay_yaml(
                existing={"working_branch": "main"},
                project_root=root,
            )
            self.assertIn(f"  - {CANONICAL_PLAN_DIR}", yaml_text)
            self.assertIn("  - .cursor/plans", yaml_text)
            self.assertNotIn("plan_search_dirs: .cursor/plans", yaml_text)

    def test_reinit_does_not_duplicate_canonical_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = overlay_path(root)
            overlay.parent.mkdir(parents=True)
            overlay.write_text(
                "plan_search_dirs:\n"
                f"  - {CANONICAL_PLAN_DIR}\n"
                "  - custom/plans\n",
                encoding="utf-8",
            )
            merged = merge_plan_search_dirs_for_emit(overlay)
            self.assertEqual(
                merged,
                [CANONICAL_PLAN_DIR, "custom/plans"],
            )


if __name__ == "__main__":
    unittest.main()
