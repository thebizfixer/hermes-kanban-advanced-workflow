"""Tests for skill directory materialization (SKILL.md + references/)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from plugin.config_overlay import PLUGIN_ROOT
from plugin.profile_bootstrap import materialize_skill_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_REFERENCES = PLUGIN_ROOT / "plugin" / "data" / "references"


class TestSkillMaterialize(unittest.TestCase):
    def test_materialize_copies_references_for_kanban_advanced(self) -> None:
        src = REPO_ROOT / "plugin" / "skills" / "kanban-advanced"
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "kanban-advanced"
            materialize_skill_dir(src, dst)
            self.assertTrue((dst / "SKILL.md").is_file())
            index = dst / "references" / "in-flight-governance-index.md"
            self.assertTrue(index.is_file(), f"missing {index}")
            self.assertIn("L0", index.read_text(encoding="utf-8"))

    def test_materialize_skill_without_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "SKILL.md").write_text("# test\n", encoding="utf-8")
            dst = Path(tmp) / "dst"
            materialize_skill_dir(src, dst)
            self.assertTrue((dst / "SKILL.md").is_file())
            self.assertFalse((dst / "references").exists())

    def test_materialize_bundles_data_references_for_bridge_skill(self) -> None:
        src = REPO_ROOT / "plugin" / "skills" / "kanban-advanced"
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "kanban-advanced"
            materialize_skill_dir(src, dst, bundle_data_references=DATA_REFERENCES)
            self.assertTrue(
                (dst / "references" / "profile-switching.md").is_file(),
                "bundled shared reference missing",
            )
            index = (dst / "references" / "in-flight-governance-index.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("## L0", index, "SSOT index should not be replaced by pointer stub")

    def test_materialize_replaces_stale_references(self) -> None:
        src = REPO_ROOT / "plugin" / "skills" / "kanban-advanced"
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "kanban-advanced"
            materialize_skill_dir(src, dst)
            stale = dst / "references" / "stale.md"
            stale.write_text("stale\n", encoding="utf-8")
            materialize_skill_dir(src, dst)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
