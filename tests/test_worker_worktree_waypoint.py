"""Documentation test: worker skill contains E021 worktree waypoint."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SKILL = ROOT / "plugin" / "skills" / "kanban-worker" / "SKILL.md"


class TestWorkerWorktreeWaypoint(unittest.TestCase):
    def test_skill_contains_e021_waypoint(self) -> None:
        text = WORKER_SKILL.read_text(encoding="utf-8")
        self.assertIn("E021_WORKTREE_INCOMPLETE", text)
        self.assertIn("worktree_setup.sh", text)
        self.assertIn("git worktree add alone is insufficient", text)
        self.assertIn("$WORKTREE_PATH/.hermes/scripts/coding_agent_invoke.sh", text)
        # Worktree-local only — HERMES_HOME fallback must not bypass E021
        waypoint_start = text.index("# Waypoint 3:")
        waypoint_end = text.index("# 4. Write .kanban-scope", waypoint_start)
        waypoint = text[waypoint_start:waypoint_end]
        self.assertNotIn("HERMES_HOME", waypoint)


if __name__ == "__main__":
    unittest.main()
