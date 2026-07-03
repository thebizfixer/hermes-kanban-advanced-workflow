"""Tests for skill_verifier.py — process-type plugin skill verification."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml
from plugin.skill_verifier import verify_process_type_skills


class TestSkillVerifier(unittest.TestCase):
    def test_all_skills_found(self) -> None:
        """Reports all skills found when all SKILL.md files exist on disk."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            plugins_dir = hermes_home / "plugins"
            plugins_dir.mkdir()
            plugin_dir = plugins_dir / "hermes-procurement"
            skills_dir = plugin_dir / "plugin" / "skills"
            
            # Create plugin.yaml
            plugin_dir.mkdir(parents=True)
            manifest = plugin_dir / "plugin.yaml"
            manifest.write_text(
                yaml.dump({
                    "provides_hooks": ["process_type:procurement"],
                    "provides_skills": ["kanban-procurement-worker", "kanban-procurement-orchestrator", "kanban-procurement-planning", "kanban-procurement-cleanup"],
                })
            )
            
            # Create all 4 skill SKILL.md files
            for skill in ["kanban-procurement-worker", "kanban-procurement-orchestrator", "kanban-procurement-planning", "kanban-procurement-cleanup"]:
                (skills_dir / skill).mkdir(parents=True)
                (skills_dir / skill / "SKILL.md").write_text(f"# {skill}\n")

            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": str(hermes_home)}
            ):
                found, missing, errors = verify_process_type_skills("procurement")

            self.assertEqual(len(found), 4)
            self.assertEqual(len(missing), 0)
            self.assertEqual(len(errors), 0)

    def test_missing_skill_reported(self) -> None:
        """Reports missing skill with fix command in output (tested via missing list)."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            plugins_dir = hermes_home / "plugins"
            plugins_dir.mkdir()
            plugin_dir = plugins_dir / "hermes-procurement"
            skills_dir = plugin_dir / "plugin" / "skills"
            
            plugin_dir.mkdir(parents=True)
            manifest = plugin_dir / "plugin.yaml"
            manifest.write_text(
                yaml.dump({
                    "provides_hooks": ["process_type:procurement"],
                    "provides_skills": ["kanban-procurement-worker", "stripe-issuing", "kanban-procurement-planning"],
                })
            )
            
            # Only create 2 of 3 skills (stripe-issuing is missing)
            (skills_dir / "kanban-procurement-worker").mkdir(parents=True)
            (skills_dir / "kanban-procurement-worker" / "SKILL.md").write_text("# worker\n")
            (skills_dir / "kanban-procurement-planning").mkdir(parents=True)
            (skills_dir / "kanban-procurement-planning" / "SKILL.md").write_text("# planning\n")
            # stripe-issuing SKILL.md NOT created

            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": str(hermes_home)}
            ):
                found, missing, errors = verify_process_type_skills("procurement")

            self.assertEqual(len(found), 2)
            self.assertEqual(len(missing), 1)
            self.assertIn("stripe-issuing", missing)
            self.assertEqual(len(errors), 0)

    def test_no_plugin_for_type(self) -> None:
        """Returns error when no plugin matches the process_type."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            plugins_dir = hermes_home / "plugins"
            plugins_dir.mkdir()
            # Create an unrelated plugin
            other_dir = plugins_dir / "hermes-other"
            other_dir.mkdir(parents=True)
            manifest = other_dir / "plugin.yaml"
            manifest.write_text(
                yaml.dump({
                    "provides_hooks": ["process_type:something-else"],
                    "provides_skills": ["other-skill"],
                })
            )

            with unittest.mock.patch.dict(
                os.environ, {"HERMES_HOME": str(hermes_home)}
            ):
                found, missing, errors = verify_process_type_skills("nonexistent")

            self.assertEqual(len(found), 0)
            self.assertEqual(len(missing), 0)
            self.assertTrue(any("No plugin found" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
