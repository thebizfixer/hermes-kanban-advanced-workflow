"""Tests for operator skill preservation on Update Plugin."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.profile_bootstrap import materialize_skill_dir
from plugin.script_materialize import (
    load_skill_manifest,
    materialize_skills_with_preservation,
    sha256_file,
)


class TestSkillPreservation(unittest.TestCase):
    def test_operator_edit_preserved_on_rematerialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_src = root / "src"
            skills_dst = root / "dst"
            skill = skills_src / "kanban-worker"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# worker v1\n", encoding="utf-8")

            materialize_skills_with_preservation(
                skills_src,
                skills_dst,
                materialize_skill_dir=materialize_skill_dir,
            )
            dst_skill = skills_dst / "kanban-worker" / "SKILL.md"
            dst_skill.write_text("# operator customized\n", encoding="utf-8")

            (skill / "SKILL.md").write_text("# worker v2 shipped\n", encoding="utf-8")
            _count, warnings = materialize_skills_with_preservation(
                skills_src,
                skills_dst,
                materialize_skill_dir=materialize_skill_dir,
            )

            self.assertTrue(any("Preserving operator-edited" in w for w in warnings))
            self.assertIn("operator customized", dst_skill.read_text(encoding="utf-8"))
            manifest = load_skill_manifest(skills_dst)
            key = "kanban-worker/SKILL.md"
            self.assertEqual(manifest[key], sha256_file(dst_skill))


if __name__ == "__main__":
    unittest.main()
