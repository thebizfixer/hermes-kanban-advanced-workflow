"""Tests for scripts/lib/cli_output_parse.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import cli_output_parse as cop  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "cli_output"


class TestCliOutputParse(unittest.TestCase):
    def test_parents_and_retries(self) -> None:
        text = (FIXTURES / "kanban_show_parents.txt").read_text(encoding="utf-8")
        self.assertEqual(cop.extract_parent_task_ids(text), ["t_abc123", "t_def456"])
        self.assertEqual(cop.extract_max_retries(text), 2)
        self.assertEqual(cop.extract_created_timestamp(text), "2026-01-15 14:30")

    def test_worktree_branch(self) -> None:
        line = (FIXTURES / "git_worktree_list.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(cop.extract_worktree_branch(line), "feature/kanban-card-1")

    def test_commit_hash(self) -> None:
        body = (FIXTURES / "card_body_commit.txt").read_text(encoding="utf-8")
        self.assertEqual(cop.extract_commit_hash_from_body(body), "abcdef1234567")

    def test_pytest_commands(self) -> None:
        plan = (FIXTURES / "plan_pytest_snippet.md").read_text(encoding="utf-8")
        cmds = cop.extract_pytest_commands(plan)
        self.assertEqual(len(cmds), 2)
        self.assertTrue(cmds[0].startswith("pytest"))

    def test_task_ids_unique_order(self) -> None:
        text = "t_one t_two t_one t_three"
        self.assertEqual(cop.extract_task_ids(text), ["t_one", "t_two", "t_three"])


if __name__ == "__main__":
    unittest.main()
