"""Tests for generate_postmortem.py plan scoping."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_postmortem as pm  # noqa: E402


class TestGeneratePostmortem(unittest.TestCase):
    def test_load_task_history_uses_plan_memory_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_dir = root / ".hermes" / "kanban" / "memory"
            mem_dir.mkdir(parents=True)
            (mem_dir / "my-plan.json").write_text(
                json.dumps({"task_ids": ["t_a", "t_b"]}),
                encoding="utf-8",
            )
            db = root / "kanban.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE tasks (id TEXT, title TEXT, status TEXT, body TEXT, plan_id TEXT)"
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_a", "A", "done", "plan_id: my-plan", "my-plan"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_b", "B", "done", "plan_id: my-plan", "my-plan"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_other", "Other", "done", "plan_id: other-plan mentions my-plan", "other-plan"),
            )
            conn.commit()
            conn.close()

            tasks, notes = pm.load_task_history(db, "my-plan", root)
            ids = {t.task_id for t in tasks}
            self.assertEqual(ids, {"t_a", "t_b"})
            self.assertTrue(any("plan memory" in n for n in notes))

    def test_build_report_includes_operator_section(self) -> None:
        report = pm.build_report(
            plan_id="p1",
            tasks=[],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
            source_notes=["scoped via plan memory task_ids"],
        )
        self.assertIn("## 9. Operator Ground Truth", report)
        self.assertIn("Data confidence", report)


if __name__ == "__main__":
    unittest.main()
